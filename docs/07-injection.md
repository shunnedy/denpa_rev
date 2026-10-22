# 07. コードインジェクション基盤

Azahar（および実機 Luma3DS）に対して、実行中のゲームへコードとデータを
注入するための足場。ツールは外部依存なし（Python標準ライブラリのみ、
`c++filt` があればシンボルが読みやすくなる）。

## 注入の3ルート

| 手段 | 反映タイミング | 用途 |
|---|---|---|
| **3GXプラグイン** | プロセス起動時 | 任意のC++コード。devkitARM + CTRPluginFramework でビルドし `sdmc/luma/plugins/<TitleID>/` に置く。実機Luma3DSと共通 |
| **LayeredFS** | 起動時 | `load/mods/<TitleID>/romfs/` にファイルを置くとベースromfsを上書き。コード不要 |
| **code.ips / code.bps** | 起動時 | exefs `.code` へのバイナリパッチ |
| **GDBスタブ** | **実行中** | メモリの読み書き。唯一ゲームを止めずに反復できる |

真のホットリロード（`.3gx` の差し替え再読込）は無い。実行中に差し替えたい場合は
GDBスタブ、または「自作ローダを3GXプラグインとして常駐させ、SDカード上の
バイナリを監視して自分でフックを張り替える」形になる。

## シンボルの出どころ

`app/lanai.crs` はモジュール名 `|static|`、つまり**メイン実行体のエクスポート
登録簿**。CRO0のセグメント表に実際のロードアドレスが入っているので、
名前付きエクスポートはすべて絶対アドレスに解決できる。

| | base | update |
|---|---|---|
| .text | `0x00100000` size `0x34550C` | `0x00100000` size `0x399900` |
| .rodata | `0x00446000` | — |
| .data | `0x0048D000` | — |
| 名前付きエクスポート | 783 | 1101 |
| うち vtable (`_ZTV`) | 20 | 26 |

全件は [`data/symbols-base.csv`](../data/symbols-base.csv) /
[`data/symbols-update.csv`](../data/symbols-update.csv)。
形式は `address,segment,name`（マングル名のまま。`c++filt` で読める）。

**アドレスの下位ビットはThumbフラグ**。奇数ならThumbコードなので、
ラベルは偶数アドレスに付ける。

Ghidraへの取り込み:

```bash
/opt/ghidra/support/analyzeHeadless /root/ghidra-projects denpafree \
  -import extracted/base/code_dec.bin -processor ARM:LE:32:v7 \
  -loader BinaryLoader -loader-baseAddr 0x00100000 \
  -postScript tools/ghidra_import_symbols.py data/symbols-base.csv
```

## 実行中の差し替えは vtable を狙う

`.text` の書き換えは2段階で妨害される。エミュレータ（Dynarmic）は変換済み
ブロックをキャッシュし、実機のARM11は命令キャッシュを持つ。どちらも
明示的な無効化なしには**古いコードが走り続けうる**。

対してvtableは `.data` 上の単なる関数ポインタ配列で、1ワード書き換えれば
次の仮想呼び出しから即反映され、元の値を書き戻せば戻る。
このゲームはC++でvtableを名前付きエクスポートしているので位置が確定している:

```
base:   ItemCommon 0x0047DC48 / ItemGoalCommon 0x0047F2EC / ItemRareCommon 0x0047F36C
        MoveObjBrokenCommon 0x00481030 / GimmickPushButtonCommon 0x00481CA8
        NpcCommon 0x004839E4 / nn::fnd::ExpHeapBase 0x00484144
update: さらに CliffCommon / FieldCommon / StaticRetire / WarpGoalCommon /
        CommonMessageArg / ContentsMessageArg が増える
```

## ツール

```bash
# シンボルを引く（接続不要）
python3 tools/inject.py --crs extracted/base_romfs/app/lanai.crs sym OpenTreasure
#   0x0017F164  ItemCommon::OpenTreasure()

# 実行中のvtableを覗く / 1エントリだけ差し替える
python3 tools/inject.py --crs ... vtget 'vtable for ItemCommon' --count 8
python3 tools/inject.py --crs ... vtset 'vtable for ItemCommon' 3 0x0017F164

# 関数を即 return させる（Thumb: MOVS r0,#imm / BX lr）
python3 tools/inject.py --crs ... retval 'ItemCommon::IsOpenItem' 1

# 自作コードを流し込んでトランポリンを張る
python3 tools/inject.py --crs ... blob 0x00500000 hook.bin
python3 tools/inject.py --crs ... tramp 'ItemCommon::Execute' 0x00500000

# 全部元に戻す（書き換え前のバイト列を journal に残してある）
python3 tools/inject.py restore
```

既定ポートは **24689**（Azaharの現行GDBスタブ。Citraは4000だった）。
`--port` で変更可能。

| ファイル | 役割 |
|---|---|
| [`tools/crosym.py`](../tools/crosym.py) | CRO0パーサ。エクスポート/インポート表、セグメント、整合性検査 |
| [`tools/rsp.py`](../tools/rsp.py) | GDB Remote Serial Protocol クライアント（gdbバイナリ不要） |
| [`tools/inject.py`](../tools/inject.py) | 上記CLI。全書き込みを journal に記録し `restore` で巻き戻す |
| [`tools/mockrsp.py`](../tools/mockrsp.py) | 擬似GDBスタブ。エミュなしで検証するため |
| [`tools/test_inject.py`](../tools/test_inject.py) | 通し自己テスト（12項目） |
| [`tools/ghidra_import_symbols.py`](../tools/ghidra_import_symbols.py) | Ghidraにシンボルを流し込む |
| [`tools/tdmpack.py`](../tools/tdmpack.py) | アーカイブ再構築（LayeredFS用） |

## 検証済みの内容

`python3 tools/test_inject.py` が擬似スタブに対して12項目すべて通過:
no-ackモードのネゴシエーション、停止理由の取得、u32の読み書き、1KBの
往復、シンボル解決、vtableの読み出しと1エントリ書き換え、
`MOVS r0,#1 / BX lr` の生成、journalによる完全な巻き戻し。

データ側も実際に通してある。`d01_msg` のUTF-16LE本文を書き換えて
`tdmpack.py` で再構築し、再デコードで反映を確認:

```
あっ！！電波人間だ、めずらしい！   →   あっ！！電波人間だ、テスト成功！
```

LZ10セクションは**リテラルのみのLZ10**として再圧縮している
（フラグバイト `0x00` + 生8バイト、の繰り返し）。マッチャを実装しなくても
正しく展開される。原本より大きくなるがLayeredFSでは問題にならない。

## 未解決・注意点

- Dynarmicが実際にどの契機でブロックを無効化するかは未確認。`.text` パッチの
  即時反映は保証されない（だからvtable推奨）
- 自作コードの置き場所: `.text` は `0x00100000`〜`0x0044550C` で直後が
  `.rodata 0x00446000` なので**隙間がほぼ無い**。3GXならプラグイン専用メモリ、
  GDB経路なら `.bss` 末尾か `nn::fnd::ExpHeapBase` から確保した領域を使う
- `.crr` にCROのハッシュがあり `ldr:ro` が検証するため、`contents*.cro` を
  自作モジュールに差し替える筋は署名検証が壁
- vtableのエントリ順（どのindexがどのメソッドか）は未確定。Ghidraで確定させる
- アドレスはbase版とupdate版で別。updateを当てるなら
  `data/symbols-update.csv` を使う

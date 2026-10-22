# denpa_rev — 電波人間のRPG FREE! 解析

ニンテンドー3DS『**電波人間のRPG FREE!**』（Genius Sonority / 任天堂、2013）の
ファイルフォーマット解析と、その成果物である自作ツール・データ一覧をまとめたリポジトリ。

## 対象ROM

| | base | update |
|---|---|---|
| プロダクトコード | `CTR-N-JF7J` | `CTR-U-JF7J` |
| タイトルID | `0004000000125D00` | `0004000E00125D00` |
| タイトル | 電波人間のRPG FREE! / Denpa Ningen RPG FREE! | 同上 |
| 発行元 | Genius Sonority Inc. | 同上 |
| romfs | 約218 MB / 124アーカイブ | 約104 MB / 185アーカイブ |
| ExeFS `.code` | 0x243F04 → 展開後 0x3A7000 | 0x276E58 → 展開後 0x3FD000 |

マニュアル用パーティション（`CTR-P-CTAP`）も同梱されている。

## このリポジトリに**入っていない**もの

ROMイメージ、展開した romfs / code.bin、モデル・テクスチャ・音声・ゲームテキスト本文などの
**ゲーム本体の著作物は一切含まれていません**。収録しているのは

- 自作の解析ツール（`tools/`）
- ファイル名・サイズ・レコード数などの**メタデータ一覧**（`data/`）
- フォーマット仕様のドキュメント（`docs/`）

だけです。解析には自分で用意した実機ROMが必要です。

## ドキュメント

| | 内容 | 状態 |
|---|---|---|
| [docs/01-rom-container.md](docs/01-rom-container.md) | NCSD / CIA / NCCH / ExeFS / RomFS / BLZ(.code圧縮) | 確定 |
| [docs/02-romfs.md](docs/02-romfs.md) | romfs の構成と統計 | 確定 |
| [docs/03-archive.md](docs/03-archive.md) | hex名アーカイブのコンテナ仕様、LZ10 | 確定 |
| [docs/04-data-tables.md](docs/04-data-tables.md) | データテーブル形式、テーブル一覧118件 | 確定（レコード内部は未解析） |
| [docs/05-text.md](docs/05-text.md) | メッセージ形式、制御コード、ルビ | 確定 |
| [docs/06-gsc.md](docs/06-gsc.md) | `.gsc` リソースラッパ | 確定 |
| [docs/07-injection.md](docs/07-injection.md) | コードインジェクション基盤、シンボルマップ | 動作確認済み |
| [docs/08-data-records.md](docs/08-data-records.md) | レコード内部、残りの形式の分類 | 一部未解明を明記 |
| [docs/09-contents-and-server.md](docs/09-contents-and-server.md) | 配信コンテンツ、キャンペーンコード、サーバAPI | 確定 |
| [docs/10-qr.md](docs/10-qr.md) | QR機能の有無（結論: 無い） | 確定 |
| [docs/11-cut-content.md](docs/11-cut-content.md) | 没データ・未使用データ | 確定 |
| [docs/12-modding.md](docs/12-modding.md) | MODの作りやすさ（実証2件） | 一部未検証 |
| [docs/13-server-protocol.md](docs/13-server-protocol.md) | サーバプロトコルとプロトタイプ実装 | `time`/`bonus_tbl` は確定 |

## ツール

いずれも Python 3 標準ライブラリのみ、外部依存なし。

```bash
# ROM の展開（復号済み .cci / .cia から）
python3 tools/ctr_extract.py ncsd game-decrypted.cci extracted
python3 tools/ctr_extract.py cia  "update-decrypted.cia" extracted
python3 tools/ctr_extract.py romfs extracted/base/romfs.bin extracted/base_romfs

# romfs 内の hex名アーカイブを読む
python3 tools/tdmarc.py info extracted/base_romfs/28480000
python3 tools/tdmarc.py x    extracted/base_romfs/28480000 out/

# アーカイブ内の全ファイル一覧を TSV で出力
python3 tools/manifest.py extracted/base_romfs > manifest-base.tsv

# メッセージテーブルをテキストに展開（漢字形／かな形）
python3 tools/gsmsg.py extracted/base_romfs/5EFE0000
python3 tools/gsmsg.py extracted/base_romfs/5EFE0000 d01_msg

# .gsc リソースラッパの中身を見る
python3 tools/gsc.py extracted/base_romfs/07E40000

# 静的モジュールのエクスポート表（= code.bin の名前付きアドレス）
python3 tools/crosym.py info    extracted/base_romfs/app/lanai.crs
python3 tools/crosym.py exports extracted/base_romfs/app/lanai.crs > symbols.csv

# 実行中のゲームに対する注入（Azahar の GDB スタブ経由）
python3 tools/inject.py --crs extracted/base_romfs/app/lanai.crs sym OpenTreasure
python3 tools/test_inject.py        # エミュ不要の自己テスト

# 配信コンテンツモジュールのイベントクラス一覧
python3 tools/crocontents.py extracted/.../contents0000.cro

# サーバのプロトタイプ（ROM内のテーブルを配信データとして返す）
python3 tools/denpa_server.py --port 8080 --table extracted/update_romfs/A9DF0000:CheckinData
python3 tools/test_server.py extracted/update_romfs/A9DF0000 CheckinData

# アーカイブ再構築（LayeredFS でのデータ改造）
python3 tools/tdmpack.py extracted/base_romfs/5EFE0000 out.bin d01_msg=patched.bin
```

`ctr_extract.py` の BLZ 展開は、別途入手した `code.bin` / `code_dec.bin` のペアに対して
MD5 が一致することを確認済み。

## 進捗

- [x] ROMコンテナの展開（NCSD/CIA/NCCH/ExeFS/RomFS）
- [x] `.code` の BLZ 展開（既知の正解と MD5 一致で検証）
- [x] romfs アーカイブのコンテナ仕様
- [x] LZ10 セクションの展開
- [x] 全17,330エントリのマニフェスト作成
- [x] データテーブルのヘッダ解析（91.0%が整合、テーブル名118件を特定）
- [x] メッセージ形式とルビ制御コード（19,344件 / 約67.8万文字を抽出可能）
- [x] `.gsc` の正体を確定（イベントスクリプトではなくマップモデルのラッパ）
- [ ] データテーブルのレコード内部（フィールド境界と型）
- [x] CRO0 の完全パース（静的モジュールのエクスポート783/1101件を絶対アドレスで特定）
- [x] コードインジェクション基盤（GDB RSPクライアント + vtable差し替え + 再構築、自己テスト12項目）
- [x] `contents*.cro` 174本のイベントクラス棚卸し（のべ551クラス、updateで+353）
- [x] QR機能の有無を確定（**存在しない** — docs/10）
- [x] サーバAPI・キャンペーンコード・デバッグ残骸の洗い出し
- [x] `LevelData` と `MapChipDB.dat` の完全デコード
- [x] Ghidraでの逆アセンブル環境（シンボル658件適用、関数248件）
- [x] `0x80000000` の正体を確定（フラグではなく「IDであって添字でない」の識別子）
- [x] ヘッダ 0x18 のブロック = レコードIDの配列（2,193件で検証、不一致0）
- [x] リソースID＝アーカイブ名の構造（上位16bit=番号 / 下位=タグ+言語マスク、309件で検証）
- [ ] 名前ハッシュ索引348件のハッシュ関数（13種×39,619候補で一致0。キーは32bit一様分布）
- [ ] レコード内の個別フィールドの意味、ブロック3/4の幅
- [x] 没データの洗い出し（ペイント機能がアーカイブごと削除、Aprilイベントのデータ欠落ほか）
- [x] データMODの実証（テキストと数値バランスの書き換え→再構築→読み戻し確認）
- [x] サーバプロトコルの解明（CSV + base64、NEX不使用）とプロトタイプ実装
- [ ] `rand3`/`rank` の40KB応答（Ｗｉ-Ｆｉコロシアムの対戦相手一覧）のフィールド構成
- [ ] 84バイトのチェックインレコードの中身
- [ ] `vendor.bin` の形式

## ライセンス

`tools/` 以下の自作コードは MIT。ドキュメントは CC BY 4.0。
解析対象のゲームおよびその著作物は Genius Sonority Inc. / 任天堂に帰属します。

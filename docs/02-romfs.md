# 02. romfs の構成

## トップレベル

base romfs（約218 MB、284ファイル / 14ディレクトリ）:

```
<8桁hexの名前>     124個  ゲームデータのアーカイブ（docs/03 参照）
app/lanai.crs           CROリンク用の静的モジュール（lanai = 開発コードネーム）
font/font_hamming_14.nftr
shader/ shaders/gs/     シェーダ
proctex_files/          プロシージャルテクスチャ
sound/sound.bcsar       サウンドアーカイブ
sound/stream/           BGM 70本（.bcstm、dspadpcm / pcm8）
sound/voice/            ボイス（common, childl28s_l）
extdata_icon/           extdata 用アイコン
.crr/                   CROの署名情報
```

update romfs（約104 MB、333ファイル / 6ディレクトリ）:

```
<8桁hexの名前>     185個
patchList.bin           パッチ対象の一覧
app/ proctex_files/ sound/
```

アーカイブのhex名は base と update で入れ替わっている（例: base の `00910000` が
update では `0091000A`）。下位バイトが世代／リビジョンを表していると思われる。

## BGM 一覧（ファイル名のみ）

`sound/stream/` の `.bcstm` 70本。開発上のマップ名が読めるため、構成を知る手がかりになる。
`BGM_OLD_DENPAISLAND_OAHU` のように `OAHU` を含むものがあり、これは電波人間のRPG3 の
開発コードネームと同じで、シリーズで素材を引き継いでいることが分かる。

## アーカイブ内のエントリ統計

[`data/manifest-base.tsv`](../data/manifest-base.tsv) /
[`data/manifest-update.tsv`](../data/manifest-update.tsv) に全件（合計 17,330 エントリ）。

| | base | update |
|---|---|---|
| アーカイブ数 | 124 | 185 |
| ZIPエントリ | 5,000 | 6,695 |
| データテーブル（LZ10） | 1,498 | 4,016 |
| 現モデルで未解釈のLZ10 | 52 | 69 |

拡張子別（base + update）:

| 拡張子 | 件数 | 内容 |
|---|---|---|
| `.bch` | 6,986 | モデル／テクスチャ（PICA200 コマンドリスト形式） |
| `.ptcl` | 2,287 | パーティクル |
| `.gsc` | 980 | マップモデルのリソースラッパ（docs/06 参照、スクリプトではない） |
| `.arc` | 453 | UIレイアウト |
| `.cro` | 174 | CTR Relocatable Object（動的モジュール＝`.code` 以外のコード） |
| `.bin` / `.dat` | 779 | データテーブル（docs/04 参照） |
| `.nftr` `.bcfnt` `.bffnt` `.act` | 26 | フォント |
| `.ctpk` `.shbin` `.icn` | 8 | テクスチャパック、シェーダ、アイコン |

`.cro` が174件あるため、ゲームロジックの相当部分が `code.bin` の外にある。
解析の際は `.code` だけを見ても足りない。

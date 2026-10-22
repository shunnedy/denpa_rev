# 06. `.gsc` — リソースラッパ

拡張子から**イベントスクリプトだと推測していたが、スクリプトではなかった**。
`.gsc` はビルド時のリソース1個を、元のソースパスとトランスフォームを添えて
包むだけの薄いコンテナ。実装は [`tools/gsc.py`](../tools/gsc.py)。

base + update で980件あり、**979件が `rom:/cg/model/map/...` 以下の
マップモデル `.bch` を包んでいる**（残り1件は別構成）。

## ヘッダ（0x180 バイト、リトルエンディアン）

```
0x0C u16 1, u16 1   バージョン
0x14 u32            ブロックオフセット（0x30 固定）
0x18 u32            パス領域の終端
0x24 u32            追加ブロックのオフセット（無いときは 0）
0x34 u32            ブロック数（2 / 3 / 16 を観測）
0x38 u32            ペイロードオフセット（常に 0x180）
0x3C u32            ペイロードサイズ
0x40 u32            ソースパスのオフセット（常に 0x54）
0x54                UTF-16LE のソースパス
(0x18の値)+0x24     スケール 3float
0x180               ペイロード（BCH）
```

スケールは**固定オフセットにない**。可変長のパスの後ろに来るため、
`0x18` の値 + 0x24 の位置から読む。base romfs の657件中656件が
`(1.0, 1.0, 1.0)`（残り1件は上記の非BCHファイル）。

## 追加ブロック

`0x3C` のペイロードサイズはファイル末尾まで届かないことが多い
（base 657件のうち634件に後続データがある）。その位置は `0x24` の値で、

```
u32 0x10
（ゼロ埋め）
u16 1, u16 1, u32 0x30
6 × float    AABB（例: -250.0, 0.0, 0.0, 250.0, ...）
```

という形。バウンディングボックスと思われる。

## パスから分かること

ソースパスには開発時のディレクトリ構成がそのまま残っている:

```
rom:/cg/model/map/map_parts/bgpt_05_volcanoA/bgpt_05_volcanoA_base.bch
rom:/cg/model/map/map_parts/bgpt_15_green/bgpt_15_green_01.bch
```

`bgpt_<番号>_<地形名>` という命名で、`volcanoA` `green` `towerA` `ruinsB`
`caveA`〜`caveD` `forestA` `forestB` `hell` `iceA` `myland` `relic`
`temple` `boutique` のようにマップの地形種別が揃う。これは docs/04 の
`MapParts*` テーブル名と一対一で対応している。

BCH 内部には Maya 由来のマテリアル名・ノード名も残る:
`DefaultShader-rs-nl` `lambert2` `lambert2-silhouette` `pPlane1` `OBBox`。

## 使い方

```bash
python3 tools/gsc.py extracted/base_romfs/07E40000
```

## 未解決

- `0x34` のブロック数の意味（2 / 3 / 16）
- `0x14` の 0x30 が指すブロックの中身
- BCH 本体の解析（PICA200 コマンドリスト形式、別途大仕事）

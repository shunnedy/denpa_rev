# 21. チェックイン復活 — 更新データは SpotPass(BOSS) 経由だった

docs/13・14 の復活サーバを Azahar の実機で試した記録と、チェックインを通すための
追加の仕組み。結論から:

- `code-update.ips`（接続先差し替え＋証明書）は**実機で動いた**。ゲームは
  `wifi.asahina.net` に届き、チェックインの handshake（`time` / `check` /
  `create` / `update`）はすべて成功した
- それでも「更新データのダウンロードに失敗しました」（MessageCommon 329）→
  「接続しなおしますか？」（355）になる。**更新データの本体はゲームサーバではなく
  任天堂の SpotPass 配信（BOSS）から来る**ためで、そこは IPS では差し替えられない
- Azahar の HLE BOSS は**ネットから何も落とさず、extdata に置かれた NsData を読む**
  だけなので、NsData ファイルを自分で作って置けばチェックインは通る見込み
  （[`tools/bossdata.py`](../tools/bossdata.py)）

## 実機で分かった handshake の正確な形式

`checkinserver` は NNID を使わない。**サポート番号（support_id）**をサーバが発行し、
以後それで識別する（MessageMenu[23]「サポート番号はチェックインから発行できます」）。
Azahar にアカウントが無くても動く。

| req | クライアントの読み方 | サーバの返し方 |
|---|---|---|
| `time` | `SUCCESS,YYYYMMDD HHMMSS` | そのまま |
| `check&support_id=` | `FUN_003eb260`: フィールド0≠`ERROR`、**フィールド1を文字列 `"true"` と比較**。true=登録済み→`update`、それ以外→`create` | support_id が空なら `SUCCESS,false`、あれば `SUCCESS,true` |
| `create` / `update` | `FUN_003eb4a4`/`FUN_003eba24`: フィールド0≠`ERROR` なら成功、残りを保存 | `SUCCESS,<support_id>,0,0,0` |
| `delete` | 同上 | `SUCCESS` |

`create`/`update` のクエリには support_id・region・create_date・update_date・
prev_update・total_num・buy_jewel・playtime と、**手持ちパーティを base64 したもの**が
付く（FUN_0038653c）。アップロードはこれだけで、コロシアム用ではない（docs/20）。

## 更新データの正体: BOSS タスク

romfs の `boss.bin`（アーカイブ `2135000A` §25、テーブル `Boss`、4レコード）:

| rec | URL | タスク名 | NsDataId |
|---|---|---|---|
| 0 | `https://npdl.cdn.nintendowifi.net/p01/nsa/bX6vTcQgC6ojhnM8/labos01/info.dat` | labos01 | 0 |
| 1 | `…/labos02/info.dat` | labos02 | 3（ID配列は 0x80000003） |
| 2 | `…/FGONLYT/resource.dat` | FGONLYT | 3 |
| 3 | `…/FGONLYT/checkin.dat` | FGONLYT | 2 |

チェックイン（`FUN_003a0cf0`）は

1. BOSS でリソース `0x80000001`（resource.dat）を取得して読み、先頭の
   `u16@0xC` をセーブ側のバージョン（プレイヤーブロック `+0x48` のビット列、
   `FUN_002cd81c`）と比較。新しければ「更新データがあります」ダイアログ
2. handshake（上の表）
3. BOSS でリソース `0x80000002`（checkin.dat）を取得し、`FUN_003a0388` が
   **GSデータテーブルとして**読む（`FUN_002bc544` → TableBase）。レコードは
   84バイトで、ROM の `CheckinData`（241件）／`Checkin_Rom`（89件）と同じ形式。
   各レコードの条件（マップグループクリア・スクリプトフラグ・日付…）を
   `FUN_0029b448` で判定し、該当するものを実行（アイテム／ジュエル付与、
   フラグ設定、イベントステージ有効化、メッセージ表示）

取得は `nn::boss`（`boss:U`、`NsDataIdList` / `ReadNsData` /
`GetNsDataHeaderInfo`）。ゲーム自身の httpc ではないので、IPS の接続先差し替えは
効かない。`NsDataIdList` のフィルタは `0x1FFFF`（datatype `0x10001` を通す）。

## Azahar での動かし方

Azahar の HLE BOSS（`core/hle/service/boss/online_service.cpp`）:

- `StartTask` / `StartBgImmediate` は**スタブ**（ダウンロードしない）
- `GetNsDataIdList` は BOSS 用 extdata アーカイブのルート `/` にあるファイルを列挙し、
  各ファイル先頭 0x34 バイトの `BossHeader` を読む。`header_length == 0x18`、
  `program_id == 実行中タイトル`、`payload_size == ファイル長 − 0x34` を要求
- `ReadNsData` は `0x34 + offset` から返す。NsDataId はファイル名ではなく
  ヘッダから取る

BOSS 用 extdata の実体はこの場所（`archive_extsavedata.cpp`: BOSS は `boss/`、通常は `user/`）:

```
<Azaharのユーザーフォルダ>/sdmc/Nintendo 3DS/00000000000000000000000000000000/
    00000000000000000000000000000000/extdata/00000000/0000125d/boss/
```

（extdata ID `0x125D` は exheader `+0x230`）。ここに `tools/bossdata.py` が作る
`00000002`（checkin.dat）と `00000003`（resource.dat）を置く。

```
python3 tools/bossdata.py build extracted/update_romfs -o out/boss
python3 tools/bossdata.py inspect out/boss/00000002
```

NsData の形式（ビッグエンディアン）:

```
0x00 u8   header_length = 0x18     0x18 u64 program id (0x0004000000125D00)
0x01 11B  0                        0x20 4B  0
0x0C u32  unknown (0)              0x24 u32 datatype = 0x10001
0x10 u32  download date            0x28 u32 payload size
0x14 4B   0                        0x2C u32 NsDataId (2 / 3)
                                   0x30 u32 version
0x34      payload（checkin.dat は CheckinData テーブルそのまま）
```

`version` はセーブの変数 `0x0B` と比較され、違えば「本日受取済み」系のフラグ
（`0x5E`）がリセットされる。

## 状態

- handshake: **実機で成功**（access.log にゲームからの4リクエストが到達）
- NsData 配置: **検証中**（このページ公開時点で未確認）。通れば「チェックイン完了」
  とボーナス表示、`CheckinData` の条件に合うイベントが有効になるはず
- `boss.bin` の URL を自前サーバに向ける romfs パッチも作ってあるが、Azahar の
  HLE BOSS は URL を使わないので不要。実機（Luma3DS）で LLE BOSS を使う場合に
  意味を持つ（その場合は BOSS コンテナの AES-CTR 暗号化と署名が必要になり、別途課題）



## BOSS タスクの流れ（コード確定）

チェックインは各リソースについて **RegisterTask → SendProperty×多数 → StartTask →
GetTaskState をポーリング → GetTaskResult → ReadNsData** という nn::boss の
手順を踏む（`FUN_003eccf4`）。送るプロパティは URL(0x07,0x3e)・タスク名(0x03,0x04)・
証明書/認証(0x10,0x11,0x12,0x3f)・ヘッダ(0x0d)・間隔/回数(0x13,0x14,0x15) など
（`FUN_00347dc0`）。Azahar の HLE はこれらを受けて **StartTask はスタブ（実際には
落とさない）**、代わりに extdata に置いた NsData を `ReadNsData` で返す。

リソースID → NsDataId の対応（`Boss` テーブルの各レコード +8）:

| リソース | GetRecordキー | 内容 | **NsDataId** |
|---|---|---|---|
| resource.dat | 0x80000001 | バージョン情報（`u16@0xC` をセーブ版と比較） | **3** |
| checkin.dat | 0x80000002 | CheckinData テーブル | **2** |

`tools/bossdata.py` が作るファイルはこの NsDataId（ヘッダ +0x2C）を 3 / 2 に
設定してある（ファイル名 `00000003` / `00000002` は任意。Azahar はヘッダから読む）。

## Wi-Fi コロシアムのボタンが出ない件（別問題）

「通信対戦」メニューに「Wi-Fiコロシアム」（MessageMenu 25）が出ないのは
**ネットワークアカウント（NNID）が無いため**と見られる。メニューはスクリプト側で
接続前に出し分けており、ストーリー進行や日付のゲートは見つからなかった。
チェックインが通ると「一部の通信機能」（MessageCommon 338）が解放される可能性が
あり、まずそこを確認する。

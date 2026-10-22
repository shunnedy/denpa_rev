# 13. サーバプロトコル（`la1.denpamen.com`）

ゲーム自身のコードから起こした仕様。実装は
[`tools/denpa_server.py`](../tools/denpa_server.py)、検証は
[`tools/test_server.py`](../tools/test_server.py)。

## 重要: NEXを使っていない

3DSのオンライン対戦は通常 任天堂のNEX（Quazal/PRUDP）基盤に乗るが、
**このゲームは使っていない**。`quazal` `prudp` `nex_` `MatchMaking`
`StationURL` `nasc` のいずれも `code.bin` に1件も存在せず、通信先は
`la1.denpamen.com` の9本だけ。**Ｗｉ-Ｆｉコロシアムも含めて、すべて
ゲーム自前のHTTPSサーバとのやりとりで完結している。**

復活のために NEX スタックを再実装する必要がない、という意味で
3DSのオンラインゲームとしては例外的に条件が良い。

## 交換の形

```
GET https://la1.denpamen.com/<endpoint>?req=<name>&...        （HTTP GETのみ）
→ ステータス 200 必須
→ 本文はカンマ区切りのプレーンテキスト
→ 第0フィールドが SUCCESS か ERROR
```

エラーは `ERROR,<コード>` の形。`ERROR,10` が実際に文字列として
埋まっている（`0x00259EB0`）。`SUCCESS,` も1つの文字列定数
（`0x003EBA18`）として存在する。

クライアント側の解析は全エンドポイントで同じ実装を共有している:

```c
本文をバッファにコピーして末尾にNUL
カンマの個数を数える                    → フィールド数 - 1
各カンマの位置を記録し、カンマをNULに置き換える
フィールドi へのポインタ = バッファ + オフセット表[i]
strcmp(フィールド0, "SUCCESS")
```

共通の応答コンテナ（レスポンスのサイズごとに2種類ある）:

```
char body[N];        N = 0x40 または 0x2800
u32  offset[M];      各フィールドの先頭オフセット
u32  count;          カンマの個数
```

### 応答バッファの上限（＝1応答の最大サイズ）

リクエストごとに固定で、コードから直接読める:

| エンドポイント / req | バッファ |
|---|---|
| `checkinserver?req=time`、`gameserver?req=total` / `rank` / `check` / `check_party` / `res_ver` | `0x40`（64バイト） |
| `checkinserver?req=bonus_tbl`、`gameserver?req=player_data` | `0x1000`（4 KB） |
| `gameserver?req=rand3` / `rank`（一覧版） | `0xA000`（40 KB） |

**48 KB ある `CheckinData` は 4 KB の応答に収まらない**ので、
大きいテーブルは分割して送られていたことになる。クエリに
`tbl=`（テーブル指定）と `t_num=`（通し番号）があるので、
これが「テーブルIDとチャンク番号」だと考えるのが自然。
**この分割の仕様は推定で、コードでの確認は未了。**

## エンドポイント

```
/checkinserver        イベント配信・時刻
/gameserver           ランキング、パーティ交換、Ｗｉ-Ｆｉコロシアム
/campaigncodeserver   キャンペーンコード（updateで追加）
/ctr_ec/              ニンテンドーeショップ連携（ジュエル購入）
/ctr_state/gs         サーバ状態
/ctr_state/gs_c  gs_j  gs_r  gs_u    同・地域別（updateで追加）
```

## クエリの組み立て

`code.bin` に残る書式文字列そのもの:

```
%s&auth_token=%s
%s%s&tbl=%u
%s%u&t_num=%d&tbl=%u
%s%u&t_num=%d&tbl=%u&pid=%s
%s&sub0=%u&pid=%s&t_num=%d&tbl=%u
%s%s&t_num=%d&tbl=%u&sub0=%d&case=%d
```

完全な形で残っている例:

```
checkinserver?req=time&tbl=checkin&prod=checkin_dev
checkinserver?req=bonus_tbl&tbl=checkin&prod=checkin_dev
checkinserver?req=check&tbl=checkin&prod=checkin_dev&support_id=
gameserver?req=res_ver
gameserver?req=check_party&pid=
gameserver?req=player_data&prod=ranking_dev&reg=0&pid=
gameserver?req=current_party&prod=ranking_dev&reg=0&sub0=
gameserver?req=top10&prod=ranking_dev&reg=0&sub0=
gameserver?req=rand3&prod=ranking_dev&reg=0
gameserver?req=rank&prod=ranking_dev&reg=0&pid=
gameserver?req=total&prod=ranking_dev&reg=0&sub0=
gameserver?req=prize_tbl&prod=ranking_dev&reg=
```

パラメータ: `req` 種別 / `tbl` テーブル / `t_num` 通し番号 /
`sub0` サブ指定 / `case` / `pid` プレイヤーID / `reg` 地域 /
`prod` プロダクト名（`checkin_dev` `ranking_dev`）/
`support_id` / `auth_token`。

## 完全に解けた応答

### `checkinserver?req=time`

```
SUCCESS,YYYYMMDD<区切り1文字>HHMMSS
```

クライアントは第1フィールドを**固定幅で**切り出す。長さ15未満なら無効と判断:

```
+0 長さ4  年      +4 長さ2  月      +6 長さ2  日
+9 長さ2  時     +11 長さ2  分     +13 長さ2  秒
```

オフセット8は読まれないので、区切りは任意の1文字（空白など）でよい。
本文全体が `ERROR,10` のときは専用のフラグが立つ（メンテナンス表示と推定）。

### `checkinserver?req=bonus_tbl` — イベント配信の本体

```
SUCCESS,<base64>
```

`SUCCESS,` の8バイトを飛ばし、残りを**base64デコード**して
**そのままテーブルローダに渡している**。デコーダは `0x0024B6A4`
（6bitずつ組み直す標準的な実装、パディング判定は変換表の `0xFD`）。
base64アルファベットは標準（`+/`）がバイナリ内に2箇所、
URLセーフ（`-_`）が1箇所ある。

つまり**配信データは docs/04 のテーブル形式そのもの**。
そしてROMには、サーバが実際に返していたデータが残っている:

| テーブル | レコード | 意味 |
|---|---|---|
| `Checkin_Rom` | 89 × 84B | 名前の通り**ROM焼き込みのフォールバック** |
| `CheckinData` | 241 × 84B | 配信された実データ |
| `CheckinEVCK18` | 122 × 84B | 配信イベント18 |
| `CheckinEVCK19` | 122 × 84B | 配信イベント19 |
| `CheckinDeliVersion` | 64 × 84B | 配信バージョン |
| `CheckinCheckinCount` | 19 × 84B | チェックイン回数 |
| `CheckinJewelBuy` | 19 × 84B | ジュエル購入 |
| `Checkin`（debug） | 1 × 84B | baseにあるデバッグ用1件 |

**8種すべてがレコード長84バイトで統一**されている。正解サンプルが
手元にあるので、配信の再現は「同じ形式のテーブルを作ってbase64で返す」
に落ちる。

### `gameserver?req=rand3` / `rank` — Ｗｉ-Ｆｉコロシアムの対戦相手一覧

応答バッファが 40 KB（`0xA000`）あるのはこれのため。

```
SUCCESS,<base64 A1>,<base64 B1>,<base64 A2>,<base64 B2>,...
```

**1相手につきフィールド2つ**で、どちらもbase64。デコード結果は
固定長スロットにそのままmemcpyされる:

| | 長さ | 格納先 |
|---|---|---|
| A | `0x20`（32バイト） | エントリ +8 |
| B | `0x4E8`（1256バイト、`0x003EA2B0` の定数） | エントリ +40 |

エントリの間隔は `0x142` u32 = 1288バイト。応答コンテナは
`body[0x2800]` + オフセット表（10,240本）+ 件数（`+0xC800`）なので、
**最大5,120相手**まで受け取れる構造。

Aが32バイト（UTF-16LEで16文字）なのでチーム名・プレイヤー名、
Bの1256バイトがパーティのデータと見るのが自然
（RPG3のQRではキャラ1体88バイトだったので、10数体＋装備で妥当な大きさ）。
**ただし2つのblobの中身そのものは未解析。**

エントリを受け取ったあとクライアントは相手ごとに
`%s%s&t_num=%d&tbl=%u&sub0=%d&case=%d` で追加リクエストを投げている。

## プロトタイプサーバ

```bash
python3 tools/denpa_server.py --port 8080 \
    --table extracted/update_romfs/A9DF0000:CheckinData
# TLSで直接受けるなら（ゲーム側をパッチした場合）
python3 tools/denpa_server.py --cert server.pem --key server.key --port 443
```

```bash
# Ｗｉ-Ｆｉコロシアムの相手を合成して配る
python3 tools/denpa_server.py --port 8080 --opponents 8
```

`tools/test_server.py` が**ゲーム側の解析規則をそのまま再現して**検証する。
22項目すべて通過:

```
req=time       200 / 第0フィールド SUCCESS / 15文字以上 /
               固定幅で切り出した年月日時分秒が妥当
req=bonus_tbl  200 / "SUCCESS," 始まり / 1応答が 0x1000 以内 /
               22チャンクを連結してbase64デコードすると
               48,360バイトの CheckinData が**バイト単位で一致** /
               デコード結果がテーブルとして妥当 / 名前とレコード数241が保持
req=rand3      第0フィールド SUCCESS / 1相手につき2フィールド /
               0xA000 以内 / 名前blobが 0x20 バイト・パーティblobが
               0x4E8 バイト / 名前が UTF-16LE として読める
その他         未知の req は ERROR,<数値> / res_ver / ctr_state / check_party
```

## 実機・エミュで動かすための残り

1. **証明書** — ゲームは `la1.denpamen.com` の証明書をピン留めしている
   （docs/07）。`0x00288E04`（ポインタ）と `0x00288E10`（長さ 0x536）の
   2ワードを自前証明書に差し替えるか、URL文字列を自前ドメインに書き換える
2. **`auth_token`** — セーブデータのキーに `auth_token`
   `failed_auth_token` `failed_auth_token_timestamp` `invalid_account`
   `unsend_account` `unsend_auth_token` があり、NNID（`act:u`）由来と
   見られる。サーバ側で検証しなければ通る可能性が高い（失敗パスが
   実装されている）が、**未検証**
3. **各応答のフィールド構成** — `time` `bonus_tbl` `rand3` は確定。
   残りの `total` / `player_data` / `check` / `check_party` /
   `current_party` / `prize_tbl` は「SUCCESS + 数値またはbase64」まで。
   対戦相手の32バイト名と1256バイトのパーティblobの**中身**も未解析
4. **84バイトのチェックインレコードの中身** — 正解サンプル8種が
   あるので突き合わせで解ける

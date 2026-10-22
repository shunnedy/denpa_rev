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

## リクエストヘッダとプレイヤー識別（解析結果）

リクエストURLに `&auth_token=<値>` が付くだけでなく、HTTPヘッダも
数値名で付けられる。ヘッダを組む関数（`0x002899EC`）が設定するのは:

| ヘッダ名 | 内容 |
|---|---|
| `101` | 32bitの値を `%016llx` で16桁hexにしたもの |
| `102` | 呼び出し側から渡される値 |
| `103` | `auth_token`（`.bss` 上のバッファから読む） |
| `104` | `801`（固定、`%d`） |
| `105` | `901`（固定、`%d`） |

`101` の値は **NNIDのprincipal ID**。`act:u` の
`GetAccountDataBlock(スロット 0xFE, サイズ 4, ブロックID 0xC)` で取得して
いる（`0x0030A8A4` → `0x003EDB68` → `0x002899EC`）。取得に失敗すると
0 が返り、**ヘッダを組む関数はその場で false を返す**:

```c
if (取得成功 && (値 != 0)) { ... ヘッダを設定 ... return true; }
return false;
```

つまり**NNIDのprincipal IDが0だとヘッダが組まれない**。これが
「NNIDなしで通信が成立するか」の分岐点になる。

関数はARMで、`0x0030A8A4`（base）/ `0x0034C238`（update）にあり、
プロローグ `f8 40 2d e9 00 00 a0 e3` が**両バイナリで一意**、
`mov r6,#0xfe` がその +0x14 にある（相対位置も一致）。

### 配布を考えるときの論点

- Azahar は `act:u` をHLEで実装しているので、**principal ID が
  非ゼロのダミー値を返す可能性がある**。その場合は何もしなくてよい。
  まず実機／エミュで `101` ヘッダに何が乗るかを観測するのが先
- 全員が同じ値になる場合、サーバ側は `101` ヘッダだけでプレイヤーを
  区別できない。`pid` クエリや別の識別子を使う設計が必要
- この取得処理そのものを書き換えてIDを差し込むアプローチは、
  アカウント識別の回避に当たるため**このリポジトリでは扱わない**

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
4. **84バイトのチェックインレコードの中身** — 列ごとの性質までは出た（下記）。
   意味の確定はチェックイン処理のコードを読む必要がある

## 84バイトのチェックインレコード（部分解析）

`CheckinData`（241レコード）の全レコードを列ごとに集計した結果:

| オフセット | 性質 | 備考 |
|---|---|---|
| +0 | 全件ID参照 | 異なる値6種 → レコード種別 |
| +4 | プール参照175 / ID 41 / 0が17 | 文字列または参照 |
| +8 | プール100 / 小さい数71 / ID 45 | |
| **+12, +24, +36, +48** | **全件 `0xD0D0D0xx`** | **未使用スロット** |
| +16, +20, +32 | ほぼ全件0 | ほぼ未使用 |
| **+28, +40, +44** | **全件0** | **未使用** |
| +52 | 全件プール参照、**241種すべて異なる** | レコード固有の参照 |
| +56 | 全件ID参照 | 異なる値18種 |
| +60, +64, +68 | プール参照・ID・数値が混在 | |
| +72, +76 | ほぼ0か小さい数 | |
| +80 | 全件ID参照 | 異なる値101種 → 報酬やアイテムの類と推定 |

84バイト中**16バイトが未使用（フィラーかゼロ固定）**なので、実際に
使われているのは17スロット程度。プールから拾える文字列には
「イベントステージ\n「」「開催中」のようなイベント告知の断片があり、
docs/05 のルビ制御コード（`\x01` + `8`/`9`/`:`）も入っている。

`+52` のオフセットが `CheckinData` では2バイト刻み（`0x40` `0x42` `0x44` …）
で並ぶので、文字列そのものではなくプール先頭に置かれた
u16配列の要素を指していると見られる。`Checkin_Rom` では刻みが違うため
テーブルによって使い方が変わる。ここは静的な突き合わせの限界で、
消費側のコードを読むのが筋。

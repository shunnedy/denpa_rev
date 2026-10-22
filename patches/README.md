# Azahar / Luma3DS 用パッチ

ゲームの接続先を `https://la1.denpamen.com/` から
`https://wifi.asahina.net/` に差し替えるIPSパッチ。

| ファイル | 対象 | URL箇所 | ピン留めする証明書 |
|---|---|---|---|
| `code-update.ips` | アップデート適用済み（`0004000E00125D00`） | 25 | 中間CA `GTS WE1`（**推奨**） |
| `code-base.ips` | アップデート**未**適用（`0004000000125D00`） | 23 | 同上 |
| `code-update-leafpin.ips` | 上の予備 | 25 | リーフ `CN=asahina.net` |

**証明書はパッチに同梱済み**なので、そのまま使えば追加作業はない。

## なぜこの形なのか

置換前後がどちらも**ちょうど25バイト**なので、文字列をその場で上書きできる。
ポインタも長さも触らないので、バイナリの整合性が崩れない。

```
https://la1.denpamen.com/    25バイト
https://wifi.asahina.net/    25バイト
```

**スキームは `https://` のまま**にしている。`http://` にすればTLSごと
無効化できてしまうが、通信の検証を落としたくないので採らない。
その代わり `https://` + ホスト16文字 + `/` = 25 という制約が付き、
**サブドメインは4文字ちょうど**でなければならない
（`asahina.net` が11文字なので 16 − 1 − 11 = 4）。

## 証明書の張り替え

ゲームは `la1.denpamen.com` の証明書を**ピン留め**している
（docs/07、`code.bin` に1334バイトのDERが埋め込まれている）。
接続先を変えるなら、新しいホストの証明書を発行したCAに
**信頼の起点を張り替える**必要がある。検証を切るのではなく、
ピン留め先を正当なCAに差し替える形。

`wifi.asahina.net`（Cloudflare）が実際に出しているチェーンは3枚で、
どれも1334バイトの枠に収まる:

| | 内容 | DER | 有効期限 |
|---|---|---|---|
| リーフ | `CN=asahina.net`（ECDSA） | 898 B | **2026-12-30**（約90日で更新） |
| 中間CA | `Google Trust Services CN=WE1` | 675 B | 2029-02-20 |
| ルート | `GTS Root R4` | 894 B | 2028-01-28 |

**中間CA（WE1）をピン留めしている**。ゲームが証明書を信頼の起点として
追加する作りなので、リーフ→WE1 の1段で検証が通り、しかも2029年まで
張り替え不要。リーフをピン留めすると90日ごとに作り直しになる。

チェーンを取り直すとき:

```bash
openssl s_client -connect wifi.asahina.net:443 -servername wifi.asahina.net \
        -showcerts </dev/null 2>/dev/null > chain.pem
# 2枚目（中間CA）を DER に変換して
python3 tools/mkpatch.py extracted/update_c0/code_dec.bin out/code.ips \
        --host wifi.asahina.net --cert inter.der
```

`mkpatch.py` が証明書のスロットと、その長さを保持しているワードを
自動で見つけて両方書き換える。

| | base | update |
|---|---|---|
| 証明書のDER | VA `0x0044FC20` | VA `0x004A2C60` |
| ポインタのワード | VA `0x00288E04` | VA `0x002AF460` |
| 長さのワード | VA `0x00288E10` | VA `0x002AF46C` |

**CAのDERは1334バイト以下でなければならない**（既存の証明書と同じ枠に
収めるため）。ECDSAの中間CAはおおむね1000バイト未満なので収まるが、
RSA 4096のルートは収まらないことがある。その場合は中間CAを使う。

## 入れ方（Azahar）

1. Azahar でゲームを右クリック → **Open Mods Location**
2. 開いたフォルダに `code.ips` という名前で置く
   （`code-update.ips` をリネーム）。`exefs/code.ips` でも読まれる
3. ゲームを起動

実機（Luma3DS）なら `sd:/luma/titles/0004000000125D00/code.ips`。

## 元に戻す

`code.ips` を削除するだけ。ROM本体は一切変更していない。

## ホスト名を変える

サブドメインは**4文字ちょうど**。長さが合わなければ `mkpatch.py` が
その場で拒否して、必要な文字数を教える。

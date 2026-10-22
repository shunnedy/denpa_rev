# サーバ側のセットアップ

ファイルは `/root/asahina-net-wifi/`（`denpa_server.py` と `tdmarc.py`）に
配置済み。以下はこちらのサンドボックスから実行できなかったので手で流す。

- systemdユニットの登録と常駐起動 → 拒否された（永続化）
- 公開DNSレコードの作成 → 同上

## 1. サービスを登録して起動

```bash
cp deploy/wifi-denpa.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now wifi-denpa.service
systemctl is-active wifi-denpa.service

curl -s 'http://127.0.0.1:8082/gameserver?req=res_ver'
#   SUCCESS,1
curl -s 'http://127.0.0.1:8082/checkinserver?req=time&tbl=checkin&prod=checkin_dev'
#   SUCCESS,20261022 233000
curl -s 'http://127.0.0.1:8082/gameserver?req=rand3&prod=ranking_dev&reg=0' | wc -c
#   相手12人ぶんのCSV
```

## 2. トンネルにサブドメインを追加

`/root/.cloudflared/config.yml` の `ingress:` に、**`http_status:404` の
キャッチオールより前**へ `deploy/cloudflared-ingress.snippet.yml` の
2行を挿入してから:

```bash
cloudflared tunnel ingress validate
cloudflared tunnel route dns asahina-net wifi.asahina.net
systemctl restart cloudflared     # asahina.net も一瞬切れる
```

ブラウザから `https://wifi.asahina.net/gameserver?req=res_ver` が
`SUCCESS,1` を返せばここまで完了。このマシンからの外向きHTTPSは
遮断されているので、確認はブラウザ側で。

## 3. 証明書のDERを書き出してパッチを作り直す

ゲームは証明書をピン留めしているので、**新しいホストの証明書を発行した
CAに張り替える**必要がある（検証は有効のまま）。

1. ブラウザで `https://wifi.asahina.net` を開く
2. 鍵アイコン → 証明書 → チェーンの**発行者（中間CA）**を選び、
   DER形式で `ca.der` として書き出す
3. パッチを作り直す

```bash
python3 tools/mkpatch.py \
    /root/modding/denpamen_free/extracted/update_c0/code_dec.bin \
    patches/code-update.ips --host wifi.asahina.net --cert ca.der
```

`ca.der` は **1334バイト以下**（ECDSAの中間CAなら収まる）。
超える場合はチェーンの別の段を試す。

## 4. ゲーム側

`patches/code-update.ips` を `code.ips` にリネームして Azahar の
Mods フォルダへ。詳細は `patches/README.md`。

## 5. 動いたかの確認

Azahar のログに `wifi.asahina.net` 宛のリクエストが出る。
サーバ側は `journalctl -u wifi-denpa -f` でアクセスが見える。
`req=res_ver` → `req=check` → `req=rand3` の順に来るはず。

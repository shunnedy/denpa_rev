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

## 3. 証明書（済み）

ブラウザのUIを触らずに `openssl` でチェーンを取得して、中間CA
（`Google Trust Services CN=WE1`、675バイト）をパッチに埋め込み済み。
DERは `/root/asahina-net-wifi/certs/` に保存してある。

```bash
# 取り直したいとき
openssl s_client -connect wifi.asahina.net:443 -servername wifi.asahina.net \
        -showcerts </dev/null 2>/dev/null > chain.pem
```

証明書が更新されても、**ピン留めしているのは中間CAなので2029年まで
作り直し不要**。GTSがWE1を切り替えた場合だけ再生成が必要。

## 4. ゲーム側

`patches/code-update.ips` を `code.ips` にリネームして Azahar の
Mods フォルダへ。詳細は `patches/README.md`。

## 5. 動いたかの確認

Azahar のログに `wifi.asahina.net` 宛のリクエストが出る。
サーバ側は `journalctl -u wifi-denpa -f` でアクセスが見える。
`req=res_ver` → `req=check` → `req=rand3` の順に来るはず。

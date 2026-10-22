# 05. メッセージ形式

ゲームテキストは docs/04 のテーブル形式そのままで格納されている。
名前が `Message*` または `*_msg` のテーブルがメッセージテーブル。
デコーダは [`tools/gsmsg.py`](../tools/gsmsg.py)。

base romfs に 127テーブル、update romfs に 253テーブル。
本文のあるメッセージは合計 **19,344件 / 約67.8万文字**。

テーブル名（30種）:

```
MessageCommon        共通
MessageMapName       マップ名          MessageMapStage    ステージ名
MessageNpcName       NPC名             MessageDenpaName   電波人間の名前
MessageMenu          メニュー          MessageTutorial    チュートリアル
MessageAction        行動              MessageContents    コンテンツ
MessageFlavor        フレーバー        MessageItemFlavor  アイテム説明
MessageQuiz          クイズ            MessageTalkCommon  共通会話
MessageTalkShop      ショップ会話      MessageTalkTower   タワー会話
MessageTalkLottery   抽選会話          MessageTalkMap     マップ会話
MessageTalkRecycle   リサイクル会話    MessageNagomiTower なごみタワー
MessageNagomiFriend  なごみフレンド
{d01,d02,d04,d07,f01,m01,s01,s02,w01,s01outf01}_msg   マップごとの会話
```

## レコード

レコード長は 12 バイト:

```
0x00 u32  メッセージ開始オフセット（blob先頭からの絶対値）
0x04 u32  メッセージ終了オフセット（排他）
0x08 u32  フラグ（`0xD0D0D0xx` の形。下位バイトのみ変化）
```

本文は**NUL終端されていない**。だから終了オフセットが明示的に持たれている。
レコード N の開始は レコード N-1 の終了 + 2 になる。

## 本文のエンコーディングと制御コード

本文は **UTF-16LE**。制御コードは UTF-16 の3ユニット
`U+0001`（エスケープ）+ オペコード文字 + u16引数 で表される。

| オペコード | 文字 | 意味 |
|---|---|---|
| `0x38` | `8` | ルビの親文字（漢字）開始 |
| `0x39` | `9` | 読み（かな）開始 |
| `0x3A` | `:` | ルビ終了 |
| `0x22` | `"` | ページ／テキストボックス区切り |
| `0x37` | `7` | 他テーブルからのテキスト差し込み |

### ルビ

```
\x01 '8' 0  電波人間  \x01 '9' 0  でんぱにんげん  \x01 ':' 0  だ、めずらしい！
```

親文字と読みが**両方データとして入っている**ので、漢字表記とかな表記の
2通りを機械的に取り出せる。小学生向けのルビ表示切り替え用と思われる。

```
漢字: ここはニンテンドーeショップの残高を使ってジュエルが買える場所だ。
かな: ここはニンテンドーeショップのざんだかをつかってジュエルがかえるばしょだ。
```

### 差し込み（オペコード `7`）

引数が後続アイテム数。各アイテムは先頭の u16 が種別:

- 種別 `3` … u16 長さ（u16ユニット数）+ インラインASCII文字列
- 種別 `2` … u16 値 + u16 フラグ

実例（`d01_msg` レコード1）:

```
\x01 '7' 3 | 3, 8, "MessageMapName\0\0" | 2, 15, 0x8000 | 3, 4, "message\0"
```

→ `MessageMapName` の `message` グループの15番（マップ名）をここに挿入。
デコード結果は

```
あっ！！電波人間だ、めずらしい！
ここは{MessageMapName/15/message}。精霊に祈りをささげる場所よ！
```

ASCII文字列がUTF-16の本文中に生バイトで埋まっているため、
blob全体を素直にUTF-16としてデコードすると
`敍獳条䵥灡慎敭` のような文字化けになる。これが差し込みトークンの正体。

## 使い方

```bash
python3 tools/gsmsg.py extracted/base_romfs/5EFE0000            # そのアーカイブの全メッセージ
python3 tools/gsmsg.py extracted/base_romfs/5EFE0000 d01_msg    # テーブル指定
```

`gsmsg.decode()` は `(漢字形, かな形, 差し込み参照の一覧)` を返す。

## 変数の差し込み

差し込みトークン（オペコード `7`）で指定される名前には、他テーブルの
参照だけでなく**実行時の変数**もある。文字列プールに生ASCIIで入っている
トークンを集計すると:

```
name        グループ名としても使われる     num / value / count / max / a_num
skill_name / sp_skill_name  とくぎ名       item / rank / level / rare
gold / jewel                通貨            fish_a / fish_b / fish_c  釣った魚
month / day / hour / minute / minutes / second   日時
target      全国討伐イベントの目標数        answer  クイズの答え
```

たとえば全国討伐イベントの告知文は

```
今回の作戦での討伐目標数は全国で「{target} 匹」よ。
目標達成時に送られる報酬は「{name}」の予定だから、頑張って！
```

という形で、目標数と報酬名を**サーバから受け取って差し込む**作りになっている
（docs/09のチェックインサーバ）。blob全体を素直にUTF-16としてデコードすると
これらのASCIIトークンが `慴杲瑥`（= "target"）のような文字化けとして現れる。

## 未解決

- フラグ `0xD0D0D0xx` の下位バイトの意味
- `voice` グループの値とボイスファイルの対応
- オペコードの全集合（`7` `8` `9` `:` `"` 以外の値も存在する可能性）
- グループ名（`message` / `voice` / `stage_name`）がテーブル内でどう区分されているか

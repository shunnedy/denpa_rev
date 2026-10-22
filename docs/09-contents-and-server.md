# 09. 配信コンテンツとサーバ

## `contents*.cro` がイベントの実体

docs/06 で `.gsc` がモデルのラッパだと分かったあと、イベントスクリプトの
実体はここだった。各モジュールはコンパイル済みC++で、**RTTIの型名文字列**が
`.rodata` にそのまま残っている。Itanium形式の `_ZTS` を外した形
——`10M02Opening` は クラス `M02Opening`——なので、実装されている
イベントオブジェクトの一覧が読める。ツールは
[`tools/crocontents.py`](../tools/crocontents.py)。

| | base | update |
|---|---|---|
| モジュール数 | 47 | 127 |
| 型名（イベントクラス） | 198 | 525 |

共通 172、**updateで追加 353、baseから消滅 26**。全174モジュールで
のべ551クラス。アップデートがどれだけコンテンツを足したかがそのまま出る。

### 命名規則

```
M02Opening              マップM02のオープニング
H01001F01Static001      マップH01 / エリア001 / 1F / 固定オブジェクト001
D01001B05BossWin        ダンジョンD01 / 001 / 地下5F / ボス撃破
D01001F01Npc0103        NPC
AfterMS0010 … AfterMS0300   メインストーリー進行後イベント
EVCK01HoleFallCommon    配信イベント(EVCK)01 の落下ギミック
```

`AfterMS` は base が `0010`〜`0040` の4件だけで、update で `0300` まで
増える。**メインストーリーの長さがアップデートで約7.5倍になっている**。

### EVCK（配信イベント）

```
EVCK01HoleFallCommon   EVCK04MoveLottery   EVCK21Common
EVCK21GimmickCommon    EVCK30MoveLottery
```

一方データ側には `checkinEVCK18_JP.bin` / `checkinEVCK19_JP.bin` しか無い
（しかも**updateのみ**、baseには無い）。コード側にEVCK01/04/21/30、
データ側に18/19が存在するので、EVCK番号は少なくとも30番台まで運用されていた。
ROMに同梱されているのはその一部だけで、残りはサーバ配信だったことになる。

### baseから消えた26件

`D01001B01Npc0014`〜`Npc0022`、`Npc0682`〜`Npc0752` のようなNPC番号と、
`ClearTelop` `RetireTelop` `RareItemDirection`。NPCの番号体系が
アップデートで振り直され、テロップ系クラスは別モジュールに移ったと見られる
（`RetireTelop` はupdateのvtable一覧に `StaticRetire` として現れる）。

## キャンペーンコード

| テーブル | レコード数 | レコード長 | 所在 |
|---|---|---|---|
| `CampaignCodeNetwork` | 137 | 88 | updateのみ |
| `CampaignCodeLocal` | 50 | 88 | updateのみ |
| `CampaignCodeAddParty` | — | — | updateのみ |
| `CampaignCodeAddPartySubItem` | — | — | updateのみ |

文字列プールには**コード入力時に表示されるメッセージ本文**が
docs/05 と同じ制御コード付きUTF-16LEで入っている。先頭レコードは
開発用のテストエントリで、「キャンペーンコードのテストです。
このメッセージが表示されているならば……せいこう」という文面が残っている。

プールにコード文字列そのもののASCII列は無く（ASCII列は
`MessageMapStage` のような差し込みトークンだけ）、**コードは数値として
レコード内に持っている**。ネットワーク系は `campaigncodeserver` で検証、
ローカル系はROM内データだけで判定していたと考えられる。

## サーバAPI

`code.bin` に残っているエンドポイント（base + update）:

```
https://la1.denpamen.com/checkinserver
https://la1.denpamen.com/gameserver
https://la1.denpamen.com/campaigncodeserver      ← updateで追加
https://la1.denpamen.com/ctr_ec/
https://la1.denpamen.com/ctr_state/gs
https://la1.denpamen.com/ctr_state/gs_c
https://la1.denpamen.com/ctr_state/gs_j          ← gs_c/gs_j/gs_r/gs_u はupdateで追加
https://la1.denpamen.com/ctr_state/gs_r
https://la1.denpamen.com/ctr_state/gs_u
```

`req=` パラメータ:

```
bonus_tbl  check  check_party  current_party  player_data
prize_tbl  rand  rank  res_ver  time  top  total
```

完全な形で残っている例:

```
checkinserver?req=time&tbl=checkin&prod=checkin_dev
checkinserver?req=bonus_tbl&tbl=checkin&prod=checkin_dev
checkinserver?req=check&tbl=checkin&prod=checkin_dev&support_id=
gameserver?req=player_data&prod=ranking_dev&reg=0&pid=
gameserver?req=current_party&prod=ranking_dev&reg=0&sub0=
gameserver?req=check_party&pid=
```

`prod=` に現れるのは **`checkin_dev` と `ranking_dev` だけ**。
製品ROMに開発用のプロダクト名が残っている。`ctr_ec/` はニンテンドー
eショップ連携（ジュエル購入）。サーバはすでに停止している。

## exheader のサービスアクセス一覧

ゲームが使える機能の上限がそのまま出る:

```
APT:A   ac:u    act:u   am:app  boss:U   cam:u    cecd:u
cfg:u   dlp:FKCL dlp:SRVR dsp::DSP  frd:u  fs:USER  gsp::Gpu
hid:USER http:C ir:USER ldr:ro  mic:u   ndm:u    news:u
nim:aoc nwm::UDS ptm:u  pxi:dev soc:U   ssl:C
$hioFIO $hostio0 $hostio1
```

読み取れること:

- `boss:U`（SpotPass）、`cecd:u`（すれちがい）、`nwm::UDS`＋`dlp`（ローカル通信・
  ダウンロードプレイ）、`frd:u`（フレンド）、`http:C`/`ssl:C`/`soc:U`（HTTPS通信）
  と、通信機能は一通り揃っている
- `nim:aoc` = 追加コンテンツ（DLC）。基本無料＋ジュエル課金の構成と整合
- `cam:u`（カメラ）と `mic:u`（マイク）がある。カメラは電波キャッチのAR用途で、
  **QR読み取りではない**（docs/10 参照）
- **`$hioFIO` `$hostio0` `$hostio1` は開発機のホストI/Oサービス**。
  製品ROMのアクセス許可リストに残っている

## 没・デバッグの残骸

| 名前 | 内容 |
|---|---|
| `DebugMapJump` | デバッグ用マップジャンプ表（レコード長48、最大11件） |
| `debugData` | レコード数2・レコード長68。2件目に `0xFF` や 10 / 100 といった値が入っており、デバッグ用の既定値セットと思われる |
| `checkin_debug_JP.bin` | チェックイン機能のデバッグ用データ（base romfsに同梱） |
| `prod=checkin_dev` / `ranking_dev` | 開発サーバのプロダクト名 |
| `$hioFIO` 等 | 開発機ホストI/Oのサービス許可 |
| `CampaignCodeNetwork` レコード0 | 「キャンペーンコードのテストです」というテスト文面 |

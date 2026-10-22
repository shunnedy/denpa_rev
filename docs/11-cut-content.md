# 11. 没データ・未使用データ

base romfs と update romfs を突き合わせ、さらに
`contents*.cro` のイベントクラス（docs/09）とデータテーブル名を
相互照合して洗い出したもの。

## ペイント機能 — アーカイブごと削除

**base romfs にデータが揃っているのに、update で跡形もなく消えている。**

アーカイブ `E4730000`（リソース番号 `0xE473`）は base にしか存在せず、
update には `0xE473` 系のアーカイブが1件もない。中身はちょうど5件:

```
paintColorData.bin    PaintColorData   36レコード × 4バイト
paintFlowerData.bin   PaintFlowerData  12レコード × 60バイト
paintItemData.bin     PaintItemData    12レコード × 64バイト
inside_03.bch         室内モデル3番
inside_03_cam.bch     そのカメラ
```

色・花・アイテムの3表と**特定の室内モデルが同じアーカイブに同梱**されている
ことから、どこかの室内（店）に入って花に色をつける類の機能だったと考えられる。

`PaintColorData` は36レコードすべてがID参照（`0x80000006` `0x80000009`
`0x8000000C` … と3ずつ増える）で、色が36種。`PaintFlowerData` の各レコードも
同じ刻みのID列を持ち、花12種 × 色のバリエーションという構造に見える。

植物側の `plantInfo` / `PlantPoint` は **base と update の両方に残っている**ので、
Paint系だけが落とされたことになる。島の植物カスタマイズが Plant系に
一本化され、Paint系は実装途中で捨てられた、という流れが自然。

## エイプリルイベント — UIはあるのにデータが無い

期間限定イベントのうち、ハロウィンとイースター（たまご探し）は
**UIクラスとデータ表の両方**が揃っている:

| イベント | クラス | データ表 |
|---|---|---|
| ハロウィン | `HalloweenPrizeAccessor` | `HalloweenPrize` ✓ |
| たまご探し | `D01EggHunt` `EggHuntPanel` `EggPrizeAccessor` `PartsEggHuntPrizeExchangeList` | `EggHunt` `EggPrize` ✓ |
| **エイプリル** | `AprilPrizePanel` `PartsAprilPrizeList` | **無い** |

4月のイベント用の賞品パネルと賞品リストのUIクラスは update に入っているのに、
対応する賞品テーブルがROMのどこにも無い。サーバ配信待ちのまま運用されなかったか、
実装途中で止まったかのどちらか。

同じく**クラスだけあって表が無い**もの:

```
FishChallengePanel / PartsFishChallengeList      釣り大会のUI
ItemPrizePanel / PartsItemPrizeSelectList        アイテム賞品の選択UI
MenuPrizeExchangeImpl / MenuPrizeExchangeNew     賞品交換メニュー
MenuColosseumPrizeImpl / MenuColosseumPrizeNew   コロシアム賞品メニュー
TimerStartCommon / StaticStopTimer               タイマー系ギミック
S01TimerStart / S01StageClear / D0XTimerAndCount タイムアタック的な仕掛け
```

※ ゲームの中核機能は `code.bin` 側にあるので、「表はあるがクラスが無い」方は
没の証拠にならない（`Omikuji` `DenpaQuiz` などは本体側実装）。
証拠として強いのは**クラスがあるのに表が無い**こちらの並び。

## updateで消えたテーブル

```
PaintColorData / PaintFlowerData / PaintItemData   上記のペイント機能
Checkin                                            チェックイン表（update では
                                                    CheckinData 等に再編）
debugData                                           デバッグ用の既定値セット
s02_msg                                             マップ s02 の会話
```

`s02_msg` が消えた一方で `S02_EventObject` / `S02_StaticEvent` は
update で**追加**されているので、マップ s02 自体は作り直されている。

## updateで消えたイベントクラス（26件）

```
D01001B01Npc0014 / 0015 / 0016 / 0018 / 0019 / 0022
D01001B01Npc0682 / 0692 / 0702 / 0732 / 0742 / 0752
D01001F01Npc0017 / 0020 / 0021 / 0562 / 0722
D01002F01Npc0025  D01003F01Npc0027  D01005B01Npc0401
D02001B01Npc0023  K01001B02Npc0028  S01OUTF01Npc0024
ClearTelop  RetireTelop  RareItemDirection
```

NPC番号の体系がアップデートで振り直されたもの（update側は `Npc0100` 以降の
番号になっている）と、テロップ系クラスの移動。`RetireTelop` は update の
vtable一覧に `StaticRetire` として現れるので、改名・再実装されたと見られる。

## 配信イベント（EVCK）の欠番

コード側に存在するEVCKクラスとROM内のデータが噛み合っていない。

| | 存在するもの |
|---|---|
| クラス | `EVCK01HoleFallCommon` `EVCK04MoveLottery` `EVCK21Common` `EVCK21GimmickCommon` `EVCK30MoveLottery` |
| データ表 | `CheckinEVCK18` `CheckinEVCK19` （**update のみ**） |

少なくとも30番台までイベント番号が運用されていたのに、ROMに同梱されたのは
18と19の2つだけ。残りはサーバ配信で、**今はもう取得できない**。
`la1.denpamen.com` は停止している（docs/09）。

## デバッグの残骸

| 名前 | 内容 |
|---|---|
| `MessageTalkCommon` レコード0 | 本文が「**ダミー**」だけ |
| `DebugMapJump` | 3レコード（recsize 48）。マップを32bitキーで指すデバッグジャンプ表。base と update で内容が同一 |
| `debugData` | レコード2件・recsize 68。2件目に `0xFF` や 10 / 100 が入ったデバッグ用既定値。update で削除 |
| `checkin_debug_JP.bin` | チェックインのデバッグデータ（base romfs に同梱） |
| `prod=checkin_dev` / `ranking_dev` | 開発サーバのプロダクト名が製品ROMのURLに残存 |
| `$hioFIO` `$hostio0` `$hostio1` | 開発機のホストI/Oサービスがexheaderのアクセス許可に残存 |
| `CampaignCodeNetwork` レコード0 | 「キャンペーンコードのテストです。このメッセージが表示されているならば……せいこう」 |
| `dummy.bch` `dummy_tex.bch` `dummy_battle.bch` | プレースホルダのモデル |

## モンスター

`enemy_*.bch` のモデルは **359ファイル・番号1〜103で欠番なし**。
`MonsterParameter` は **439レコード**あるので、1体のモデルに複数の
パラメータ（レベル帯・イベント専用など）が割り当てられている。
`MonsterParameterMain` / `Extra` / `RegularEvent` / `SpecialEvent` と
4つに分かれているのは update からで、base は `MonsterParameter` 1本だけ。
モデル側に欠番がないため、**モデルだけ残った没モンスターは無い**。

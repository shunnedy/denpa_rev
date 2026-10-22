# 04. データテーブル形式（部分解析）

アーカイブのセクションのうち ZIP でないものは、LZ10 展開すると
Genius Sonority 独自のテーブル形式になる。base + update で 5,514 セクション。

## ヘッダ（確度: 中）

数値テーブルについては次のモデルで大半が整合する。

```
0x00 u32  レコード数
0x04 u32  0x0C            常に同じ値
0x08 u32  0x40            テーブル名のオフセット（＝レコード領域の開始）
0x0C u32  テーブル種別ID
0x10 u32  主ブロックのオフセット
0x14 u32  主ブロックのサイズ   （= レコード数 × レコード長）
0x18 u32  副ブロックのオフセット（無いときは 0）
0x1C u32  副ブロックのサイズ
0x28 u32  展開後の全体サイズ
0x38 u32  テーブル名の長さ（NUL込み）
0x40      テーブル名（ASCII, NUL終端）
```

検証できている例:

| テーブル | レコード数 | 主ブロック | レコード長 |
|---|---|---|---|
| `AreaInfo` | 2 | 0x50 / 0x18 | 12 |
| `CannonParameter` | 1 | 0x60 / 0x0C | 12 |
| `BattleFieldContents` | 15 | 0x60 / 0xB4 | 12 |

`0x28` の値が展開後サイズと一致すること、`主ブロックサイズ ÷ レコード数` が
整数のレコード長になることは多数のテーブルで確認済み。

## 未解決

- 全体の約13%（base 52 / update 69 セクション）はこのモデルで名前が取れない。
  その多くは**複数テーブルを1ブロックに持つメッセージ系**で、レイアウトが別物（docs/05 参照）
- `0x0C` のテーブル種別IDの意味、`0x04` が常に `0x0C` である理由は不明
- 副ブロックの用途（文字列プールと推定）は未確定
- レコード内のフィールド境界・型は未解析。フィールド定義がROM内のどこかにあるのか、
  `.code` 側にハードコードされているのかも不明

## 判明しているテーブル名（80件、一部は誤パース）

```
AkariGuide            AreaInfo              BattleConfig          BattleFieldContents
CannonParameter       CecLampIgnore         ChallengeSetting      ClearReward
ContentsDef           DebugMapJump          DenpaQuiz             DesignedMap
DoubleupProbability   EggHunt               EggPrize              FishingPoint
FishingPointSetting   FoodCollect           GimmickPattern        HalloweenPrize
JumpSetting           Lottery               MapCamera             MapChara
MapData               MapDataResource       MapEnv                MapGroup
MapLot                MapPartsBoutique      MapPartsCaveA-D       MapPartsForestA/B
MapPartsGreen         MapPartsHell          MapPartsIceA          MapPartsMyland
MapPartsRelic         MapPartsRuinsA/B      MapPartsTemple(B,C)   MapPartsTowerA/B
MapPartsType          MapPartsVolcanoA      MapResource           MapSurfaceIgnore
MissionReward         MoneyOffering         MonsterGroup          NpcPattern
Omikuji               PlantPoint            QuestionSetting       QuizSelector
RankPeriod            RepulseAward          RescueAward           ResourceFileList
S01Direction          Shop                  ShopItem              SweetsRecipe
TableResource         TeamConfig            TimerReward           TreasureConcentration
TreasureGroup         TreasureMonsterDirection  TreasureNum
```

`B0D0` `j0W0` `mask_in` `symbol` `zz` は誤パース（名前フィールドに別データが入っている）。

`DebugMapJump` `debugData.bin` のようなデバッグ用テーブルが製品ROMに残っている。

## ZIPエントリ側のデータファイル（210件）

テーブルとは別に、ZIP内に `.bin` / `.dat` としてデータが入っているものがある。
主なもの（全件は [`data/manifest-base.tsv`](../data/manifest-base.tsv) 参照）:

**キャラクター生成・電波人間のパーツ**
`antennaGroup.bin` `antennaModel.bin` `bodyColorData.bin` `bodyColorGenetic.bin`
`bodyData.bin` `bodyPattern.bin` `faceData.bin` `headData.bin` `paintColorData.bin`
`createSelect*.bin`（Antenna / Body / BodyColor / Brow / Cheek / Equip / Eye / Face /
FaceColor / Glass / HairColor / Head / Mouth / Name / Nose の16種）

**戦闘・成長**
`battleParameter.bin` `battleField.bin` `levelData.bin` `levelStatusData.bin`
`parameterCap.bin` `classUpPlayerPoints.bin` `boostParameter.bin` `skillPreset.bin`
`monsterParameterMain.bin` `monsterParameterExtra.bin`
`monsterParameterRegularEvent.bin` `monsterParameterSpecialEvent.bin`
`monsterBrain.bin` `monsterDesign.bin` `boss.bin` `encount.bin` `animReaction.bin`

**装備・アイテム**
`equipInfo_back/cloth/face/foot/hand/neck.bin` `itemDataCore.bin` `useItemInfo.bin`
`foodData.bin` `treasureData.bin` `fukubukuroData.bin` `recycleSetting.bin` `vendor.bin`

**レアガチャ・抽選**
`lotRareDenpa_Normal.bin` `lotRareDenpa_Geki.bin` `lotRareDenpa_Mac.bin`
`lotRareDenpa_Collabo.bin` `lotRareDenpa_Delivery.bin`
`lotRareDenpa_Limited.bin` + `lotRareDenpa_Limited_1`〜`_12.bin`
`createRarityLot.bin` `raregetParameter.bin` `lottery_npc_00`〜`02.bin`

**配信・チェックイン（サーバ連動）**
`checkinData_JP.bin` `checkin_Rom_JP.bin` `checkin_debug_JP.bin`
`checkinCheckinCount_JP.bin` `checkinDeliVersion_JP.bin` `checkinJewelBuy_JP.bin`
`checkinEVCK18_JP.bin` `checkinEVCK19_JP.bin` `checkinOffsetTime.bin`
`campaignCatch_JP.bin` `campaignCharacter.bin` `campaignCodeAddParty.bin`
`campaignCodeAddPartySubItem.bin` `campaignCodeLocal_JP.bin` `campaignCodeNetwork_JP.bin`
`useByDate.bin`

**マップ・イベント**
`{d01..d08,f01,h01,k01,m01,m02,s01,s02,w01,w02}_EventObject.bin` / `_StaticEvent.bin`
`mapObject.bin` `mapPartsCommon.bin` `floorData.bin` `worldmapParts.bin` `MapChipDB.dat`

**家・なごみ（ハウジング）**
`housePresent.bin` `houseRequest.bin` `houseSetting.bin` `houseWaitMotion.bin`
`interiorInfo.bin` `exteriorInfo.bin` `plantInfo.bin`
`nagomiAction.bin` `nagomi{Catch,House,Town}{Item,List}.bin`

**釣り**
`fishData.bin` `fishingHook.bin` `fishingLevel.bin` `fishingRod.bin`

**コロシアム・ランキング・すれちがい**
`colosseumDenpa.bin` `colosseumDenpaTeam_rank1..5_02..12.bin`（30件）
`rankingConfig.bin` `rankingPrize.bin` `rankingStamina.bin` `rankingWinPrize.bin`
`streetPassWinPrize.bin` `statusCommunity.bin`

`campaignCode*` と `checkin*` が揃っていることから、配信アイテムはサーバ配信と
コード入力の両系統があったことが分かる。`useByDate.bin` は配信物の有効期限と推定。

`lotRareDenpa_Collabo.bin` はコラボ限定レア電波人間の抽選テーブルと思われる。

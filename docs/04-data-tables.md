# 04. データテーブル形式

アーカイブのセクションのうち ZIP でないものは、LZ10 展開すると
Genius Sonority 独自のテーブル形式になる。base + update で 5,635 セクション。

## ヘッダ（0x40 バイト、リトルエンディアン）

```
0x00 u32  レコード数
0x04 u32  1レコードのバイト数
0x08 u32  文字列プールのオフセット   常に 0x40
0x0C u32  文字列プールのサイズ
0x10 u32  レコード配列のオフセット   （プール直後、0x10境界に整列）
0x14 u32  レコード配列のサイズ       （= レコード数 × レコード長）
0x18 u32  **レコードIDの配列**（u32×レコード数） / 0x1C u32 サイズ
0x20 u32  ブロック3 オフセット / 0x24 u32 サイズ
0x28 u32  ブロック4 オフセット / 0x2C u32 サイズ
0x34 u32  **テーブル名のオフセット（プール先頭からの相対値）**
0x38 u32  プール内の最後のエントリのオフセット
```

ハマりどころは **0x34**。テーブル名はプールの途中にあり、プール先頭（0x40）には
別のデータが入っている。`0x40` をそのまま名前として読むと、文字列データや
UTF-16 の日本語テキストを ASCII として読んでしまい `B0D0` `j0W0` のような
意味不明な名前になる（初期の解析でこれを踏んだ）。

レコード内のオフセット値は**blob先頭からの絶対値**で、名前オフセットだけが
プール相対であることにも注意。

0x18 のブロックが**レコードIDの配列**であることはコード側で確定した
（docs/08「IDと添字の区別」）。`サイズ = レコード数 × 4` が、
IDを持つ2,193テーブルすべてで一致し、不一致は0件。残り2,935テーブルは
この配列を持たず、添字だけで引かれる。

検証: 5,635セクション中 5,128（91.0%）が
「プールオフセット = 0x40」「レコード配列サイズ = レコード数 × レコード長」
「0x40 + 0x34の値 に印字可能ASCIIの名前がある」を同時に満たす。
残り507は別レイアウトか、テーブルではないデータ。

## 判明しているテーブル名（118件）

```
AkariGuide            AreaInfo              BattleConfig          BattleFieldContents
CannonParameter       CecLampIgnore         ChallengeSetting      ClearReward
ColorData             ConditionData         ContentsDef           DebugMapJump
DenpaCustom           DenpaQuiz             DesignedMap           DoubleupProbability
EggHunt               EggPrize              FishingPoint          FishingPointSetting
FoodCollect           GimmickPattern        HalloweenPrize        ItemData
JewelShopInfo         JumpSetting           Lottery               LotteryItem
MapCamera             MapChara              MapData               MapDataResource
MapEnv                MapGroup              MapLot                MapResource
MapStage              MapStageIntegration   MapSurfaceIgnore      MissionReward
MoneyOffering         MonsterGroup          MonsterParameter      NpcParameter
NpcPattern            Omikuji               PlantPoint            QuestionSetting
QuizSelector          RankPeriod            RepulseAward          RescueAward
ResourceFileList      S01Direction          Shop                  ShopIsland
ShopItem              SkillData             SweetsRecipe          TableResource
TeamConfig            TimerReward           TreasureConcentration TreasureGroup
TreasureMonsterDirection  TreasureNum       layout_contents

MapParts{Boutique,CaveA-D,ForestA,ForestB,Green,Hell,IceA,Myland,Relic,
         RuinsA,RuinsB,Temple,TempleB,TempleC,TowerA,TowerB,Type,VolcanoA}

Message{Action,Common,Contents,DenpaName,Flavor,ItemFlavor,MapName,MapStage,Menu,
        NagomiFriend,NagomiTower,NpcName,Quiz,TalkCommon,TalkLottery,TalkMap,
        TalkRecycle,TalkShop,TalkTower,Tutorial}

{d01,d02,d04,d07,f01,m01,s01,s02,w01,s01outf01}_msg
```

全件のレコード数・レコード長は
[`data/manifest-base.tsv`](../data/manifest-base.tsv) /
[`data/manifest-update.tsv`](../data/manifest-update.tsv) の
`records` / `rec_size` / `pool_size` 列にある。

`DebugMapJump` のようなデバッグ用テーブルが製品ROMに残っている。

## 未解決

- レコード内のフィールド境界・型。フィールド定義がROM内にあるのか、
  `.code` / `.cro` 側にハードコードされているのかも不明
- ブロック2〜4 の用途
- 0x38 の値の正確な意味
- 残り507セクションのレイアウト

## ZIPエントリ側のデータファイル（210件）

テーブルとは別に、ZIP内に `.bin` / `.dat` としてデータが入っているものがある。
主なもの（全件はマニフェスト参照）:

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

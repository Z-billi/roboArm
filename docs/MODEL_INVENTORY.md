# 模型文件清单

日期：2026-10-27。列出本次发布的 29 个 CAD 文件，SHA-256 对应仓库内发布版本。

| 文件 | 字节数 | SHA-256 |
| --- | ---: | --- |
| `42步进电机.SLDPRT` | 201725 | `f46d62e900e32ebe4214d59f897dd32a64e958ce0d38940dcd39043071d67c27` |
| `42步进电机.STEP` | 104893 | `313b7541cdae8e4d1bb3a888b0de0dbf6749171068ccf9e43e66d70a153a6bb8` |
| `两侧传动大齿轮.SLDPRT` | 914562 | `ea2dd4e7d0a7583ce1d09401f65090c86acbc9b66d9e89e452c22b7968fecaf6` |
| `两侧传动齿轮.SLDPRT` | 545349 | `b236420ca858f278a1451fa71e7fdd68e4cd20491f203a4dfd5a38c252247b7c` |
| `两侧传动齿轮.STEP` | 523341 | `a372fa5cb883851886a4045660e151956301e0a4557f7b87202621bd33eaf4bb` |
| `中臂膀.SLDPRT` | 338495 | `90b9ddb9e6c978397d1e180150432023a808ef17f5f20e592919066d65059826` |
| `圆柱连接键.SLDPRT` | 91962 | `6fe36ae176df54df10a2b14d39fdba9bb2cc683da097255813724384bd524187` |
| `大臂.SLDPRT` | 294624 | `72d4ac8eedbaa1b0a45d54f1633739280da0a058a68b57388af1aa6f30edff4e` |
| `大齿轮.SLDPRT` | 921769 | `981f1b4d4ac3b4c2e4ec9b71b83cc59397abf64dadd5cd76225a9736efcca9ce` |
| `夹爪.SLDASM` | 107309 | `2b804eae15634af01bfd9b3c3679d60fc02946a6260893a055756d0a989f30a1` |
| `夹爪体积块.SLDPRT` | 64717 | `27a2e2d93bd58f8a736156bde634d478da78d16587d955f3d476339c544c250e` |
| `夹爪零件1.SLDPRT` | 109961 | `9b609b421be92969a6b713eb920d0292b6bd7dce8cfa9c532bc90dd0bf365936` |
| `夹爪零件2.SLDPRT` | 250210 | `f200efb53ca2f5af3f78600f91d6363d2135f0a25a198b4436579c79226c372f` |
| `小齿轮帽.SLDPRT` | 415239 | `c3512b44a67b519acd1e2475f51177159203ddd846e13547fab3a695ea6e714f` |
| `小齿轮帽.STEP` | 384289 | `3fca0cce27ee564957a5efcc257ac271774cae1969657b4cd35915d56a28c4fc` |
| `底座.SLDPRT` | 885509 | `ab6b84b281d27dd0a9b34a96d567bf40b72d0aeb96b157dbece675e25561e69f` |
| `座体.SLDPRT` | 667676 | `515ac1d1b4aba19b9760478f6349cc07d13e62c6d5c8be7dcd148a85f8c72001` |
| `总装配体.STEP` | 164170 | `1cb6cf531840c3b56fd67f00f141b7ba6b1028390c4341ece562eb7cc59ee1f3` |
| `末端连接键.SLDPRT` | 209228 | `b14ca1258ee302004064b5c7eab779bcf04c2ec66f123a33d912e9a4b8e9493a` |
| `装配体1.SLDASM` | 1092701 | `fb3c89881fe108ed5f7597298cb57510ad38dbfbadb7ae62f5426c0391ca2c46` |
| `装配体2.SLDASM` | 1719844 | `a7dd30601c9951c288b7008266b9921a1e7d847f3f20828eb504c22f6a62f0b8` |
| `轴承内圈.SLDPRT` | 106471 | `1b85945879cdc516639ebb7132dba78bee30282ccffa10cbab28a357714d60d7` |
| `轴承外圈.SLDPRT` | 254633 | `996b0f1a6f8908cbbc368fa9f4eee8e462c98259513388067908f6e34e4f888e` |
| `连接三角.SLDPRT` | 170989 | `24b690c1f7162b962c0a49b810e881bf8546e3f2ff874f2fc90a0ccf097cfbaa` |
| `连杆.SLDPRT` | 208177 | `57beeb355ca0eb51daa64c0272b68cb585f25064774a3016e5033ddb95a469e4` |
| `连杆2.SLDPRT` | 85889 | `0030f9f5fcb7e4634f8e218466a31aa90542c3b238e943e3ea87972ccc169b73` |
| `连杆2（2）.SLDPRT` | 125737 | `8fdb20b0c67f6dff752cda95bd588dcc78e1cd37659a53c39c71cdfcd87cf702` |
| `连杆3.SLDPRT` | 202516 | `3abd53b6ab93a8849f656aced2264c40f2752d2cf9bdf2b8c1eb31bc2733cd5f` |
| `连杆摆动块.SLDPRT` | 234249 | `b4d1e8caac5c40809064a28ed2f169e38ac570b0a4a0fb29ea45d935a8b4d551` |

## 总装配体 STEP 外部依赖

由 STEP 的 `DOCUMENT_FILE` 记录提取；仅检查同目录文件是否存在，不代表 CAD 几何和装配验证。

| 引用文件 | 当前目录 |
| --- | --- |
| `42步进电机.STEP` | 存在 |
| `两侧传动大齿轮.STEP` | 缺失 |
| `两侧传动齿轮.STEP` | 存在 |
| `中臂膀.STEP` | 缺失 |
| `大臂.STEP` | 缺失 |
| `大齿轮.STEP` | 缺失 |
| `夹爪.STEP` | 缺失 |
| `小齿轮帽.STEP` | 存在 |
| `底座.STEP` | 缺失 |
| `座体.STEP` | 缺失 |
| `末端连接键.STEP` | 缺失 |
| `轴承外圈.STEP` | 缺失 |
| `连接三角.STEP` | 缺失 |
| `连杆.STEP` | 缺失 |
| `连杆2（2）.STEP` | 缺失 |
| `连杆3.STEP` | 缺失 |
| `连杆摆动块.STEP` | 缺失 |

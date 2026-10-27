| 載體 | 方法 | 負載 | payload (KiB) | α_video | bpp（嵌入幀） | PSNR 舊算法 | PSNR 全片 dB 平均 | **PSNR MSE-first 全片** | PSNR MSE-first 嵌入幀 | 無損基準→stego | 可逆 |
| :--- | :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :---: |
| synthetic_flat128_1920x1080_24f.y4m | coltuc | load=10% | 151 | 0.125 | 0.1993 | 91.4339 | 94.8131 | **67.1784** | 58.1475 | +4535.55% | ✅ |
| synthetic_flat128_1920x1080_24f.y4m | coltuc | load=40% | 605 | 0.417 | 0.2392 | 74.3006 | 82.2465 | **61.1497** | 57.3475 | +17898.43% | ✅ |
| synthetic_flat128_1920x1080_24f.y4m | coltuc | load=80% | 1211 | 0.833 | 0.2392 | 57.1759 | 64.6032 | **58.1446** | 57.3528 | +35757.82% | ✅ |
| synthetic_flat128_1920x1080_24f.y4m | coltuc | load=100% | 1514 | 1.000 | 0.2492 | 57.1743 | 57.1732 | **57.1732** | 57.1732 | +44609.39% | ✅ |
| synthetic_flat128_1920x1080_24f.y4m | coltuc | payload=256KiB | 256 | 0.208 | 0.2023 | 85.3087 | 91.5864 | **64.8948** | 58.0824 | +7657.25% | ✅ |
| synthetic_flat128_1920x1080_24f.y4m | coltuc | payload=1024KiB | 1024 | 0.708 | 0.2380 | 58.4234 | 69.9264 | **58.8726** | 57.3750 | +30265.61% | ✅ |
| synthetic_flat128_1920x1080_24f.y4m | checkerboard | load=10% | 606 | 0.125 | 0.7977 | 90.2323 | 94.0606 | **61.1591** | 52.1282 | +10748.90% | ✅ |
| synthetic_flat128_1920x1080_24f.y4m | checkerboard | load=40% | 2423 | 0.417 | 0.9572 | 70.6909 | 79.7393 | **55.1320** | 51.3299 | +41589.78% | ✅ |
| synthetic_flat128_1920x1080_24f.y4m | checkerboard | load=80% | 4846 | 0.833 | 0.9572 | 51.1566 | 59.5866 | **52.1233** | 51.3315 | +82149.85% | ✅ |
| synthetic_flat128_1920x1080_24f.y4m | checkerboard | load=100% | 6057 | 1.000 | 0.9971 | 51.1525 | 51.1537 | **51.1537** | 51.1537 | +102484.43% | ✅ |
| synthetic_flat128_1920x1080_24f.y4m | checkerboard | payload=256KiB | 256 | 0.083 | 0.5057 | 90.2314 | 96.6958 | **64.8964** | 54.1046 | +4312.54% | ✅ |
| synthetic_flat128_1920x1080_24f.y4m | checkerboard | payload=1024KiB | 1024 | 0.208 | 0.8091 | 82.9469 | 90.3416 | **58.8746** | 52.0622 | +17159.95% | ✅ |
| synthetic_hgrad_1920x1080_24f.y4m | coltuc | load=10% | 151 | 0.125 | 0.1993 | 91.4316 | 94.8109 | **67.1637** | 58.1328 | +104.04% | ✅ |
| synthetic_hgrad_1920x1080_24f.y4m | coltuc | load=40% | 605 | 0.417 | 0.2392 | 74.2935 | 82.2413 | **61.1374** | 57.3353 | +673.77% | ✅ |
| synthetic_hgrad_1920x1080_24f.y4m | coltuc | load=80% | 1211 | 0.833 | 0.2392 | 57.1641 | 64.5915 | **58.1323** | 57.3405 | +1435.56% | ✅ |
| synthetic_hgrad_1920x1080_24f.y4m | coltuc | load=100% | 1514 | 1.000 | 0.2492 | 57.1625 | 57.1614 | **57.1614** | 57.1614 | +1809.62% | ✅ |
| synthetic_hgrad_1920x1080_24f.y4m | coltuc | payload=256KiB | 256 | 0.208 | 0.2023 | 85.2680 | 91.5765 | **64.8803** | 58.0679 | +237.04% | ✅ |
| synthetic_hgrad_1920x1080_24f.y4m | coltuc | payload=1024KiB | 1024 | 0.708 | 0.2380 | 58.4041 | 69.9165 | **58.8603** | 57.3627 | +1200.99% | ✅ |
| synthetic_hgrad_1920x1080_24f.y4m | checkerboard | load=10% | 606 | 0.125 | 0.7977 | 90.0534 | 93.9178 | **60.1311** | 51.1002 | +428.20% | ✅ |
| synthetic_hgrad_1920x1080_24f.y4m | checkerboard | load=40% | 2423 | 0.417 | 0.9572 | 70.1548 | 79.3459 | **54.2049** | 50.4028 | +1855.02% | ✅ |
| synthetic_hgrad_1920x1080_24f.y4m | checkerboard | load=80% | 4846 | 0.833 | 0.9572 | 50.2621 | 58.8109 | **51.2212** | 50.4294 | +3735.82% | ✅ |
| synthetic_hgrad_1920x1080_24f.y4m | checkerboard | load=100% | 6057 | 1.000 | 0.9971 | 50.2592 | 50.2600 | **50.2600** | 50.2600 | +4665.70% | ✅ |
| synthetic_hgrad_1920x1080_24f.y4m | checkerboard | payload=256KiB | 256 | 0.083 | 0.5057 | 90.0524 | 96.5899 | **63.9901** | 53.1983 | +120.93% | ✅ |
| synthetic_hgrad_1920x1080_24f.y4m | checkerboard | payload=1024KiB | 1024 | 0.208 | 0.8091 | 82.4421 | 90.1250 | **57.9704** | 51.1580 | +728.59% | ✅ |
| synthetic_dgrad_1920x1080_24f.y4m | coltuc | load=10% | 151 | 0.125 | 0.1991 | 91.2945 | 94.7248 | **66.4759** | 57.4450 | +707.48% | ✅ |
| synthetic_dgrad_1920x1080_24f.y4m | coltuc | load=40% | 605 | 0.417 | 0.2389 | 73.8858 | 81.9568 | **60.4546** | 56.6525 | +2225.96% | ✅ |
| synthetic_dgrad_1920x1080_24f.y4m | coltuc | load=80% | 1210 | 0.833 | 0.2389 | 56.4811 | 64.0207 | **57.4482** | 56.6564 | +4276.89% | ✅ |
| synthetic_dgrad_1920x1080_24f.y4m | coltuc | load=100% | 1512 | 1.000 | 0.2489 | 56.4816 | 56.4783 | **56.4783** | 56.4783 | +5080.04% | ✅ |
| synthetic_dgrad_1920x1080_24f.y4m | coltuc | payload=256KiB | 256 | 0.208 | 0.2023 | 84.9271 | 91.4197 | **64.1892** | 57.3768 | +1079.39% | ✅ |
| synthetic_dgrad_1920x1080_24f.y4m | coltuc | payload=1024KiB | 1024 | 0.708 | 0.2380 | 57.6578 | 69.4187 | **58.1712** | 56.6736 | +3658.54% | ✅ |
| synthetic_dgrad_1920x1080_24f.y4m | checkerboard | load=10% | 604 | 0.125 | 0.7952 | 90.0439 | 93.9299 | **60.1640** | 51.1331 | +1589.92% | ✅ |
| synthetic_dgrad_1920x1080_24f.y4m | checkerboard | load=40% | 2415 | 0.417 | 0.9542 | 70.1270 | 79.3392 | **54.1796** | 50.3775 | +5333.80% | ✅ |
| synthetic_dgrad_1920x1080_24f.y4m | checkerboard | load=80% | 4831 | 0.833 | 0.9542 | 50.2161 | 58.7910 | **51.1813** | 50.3895 | +10295.22% | ✅ |
| synthetic_dgrad_1920x1080_24f.y4m | checkerboard | load=100% | 6038 | 1.000 | 0.9939 | 50.2122 | 50.2143 | **50.2143** | 50.2143 | +12439.14% | ✅ |
| synthetic_dgrad_1920x1080_24f.y4m | checkerboard | payload=256KiB | 256 | 0.083 | 0.5057 | 90.0431 | 96.5692 | **63.9362** | 53.1444 | +780.92% | ✅ |
| synthetic_dgrad_1920x1080_24f.y4m | checkerboard | payload=1024KiB | 1024 | 0.208 | 0.8091 | 82.3341 | 90.0966 | **57.9169** | 51.1045 | +2404.75% | ✅ |
| synthetic_shapes_1920x1080_24f.y4m | coltuc | load=10% | 151 | 0.125 | 0.1991 | 91.3058 | 94.7317 | **66.5303** | 57.4994 | +192.38% | ✅ |
| synthetic_shapes_1920x1080_24f.y4m | coltuc | load=40% | 605 | 0.417 | 0.2389 | 73.9149 | 81.9793 | **60.5083** | 56.7062 | +633.11% | ✅ |
| synthetic_shapes_1920x1080_24f.y4m | coltuc | load=80% | 1209 | 0.833 | 0.2389 | 56.5323 | 64.0625 | **57.5005** | 56.7087 | +1226.92% | ✅ |
| synthetic_shapes_1920x1080_24f.y4m | coltuc | load=100% | 1512 | 1.000 | 0.2488 | 56.5328 | 56.5324 | **56.5324** | 56.5324 | +1466.57% | ✅ |
| synthetic_shapes_1920x1080_24f.y4m | coltuc | payload=256KiB | 256 | 0.208 | 0.2023 | 84.9218 | 91.4257 | **64.2430** | 57.4306 | +299.75% | ✅ |
| synthetic_shapes_1920x1080_24f.y4m | coltuc | payload=1024KiB | 1024 | 0.708 | 0.2380 | 57.6834 | 69.4508 | **58.2222** | 56.7246 | +1045.04% | ✅ |
| synthetic_shapes_1920x1080_24f.y4m | checkerboard | load=10% | 603 | 0.125 | 0.7936 | 90.0498 | 93.9342 | **60.1925** | 51.1616 | +443.12% | ✅ |
| synthetic_shapes_1920x1080_24f.y4m | checkerboard | load=40% | 2411 | 0.417 | 0.9523 | 70.1414 | 79.3490 | **54.2021** | 50.4000 | +1516.62% | ✅ |
| synthetic_shapes_1920x1080_24f.y4m | checkerboard | load=80% | 4821 | 0.833 | 0.9523 | 50.2379 | 58.8101 | **51.2020** | 50.4102 | +2936.01% | ✅ |
| synthetic_shapes_1920x1080_24f.y4m | checkerboard | load=100% | 6026 | 1.000 | 0.9920 | 50.2334 | 50.2358 | **50.2358** | 50.2358 | +3553.41% | ✅ |
| synthetic_shapes_1920x1080_24f.y4m | checkerboard | payload=256KiB | 256 | 0.083 | 0.5057 | 90.0490 | 96.5543 | **63.9574** | 53.1656 | +212.87% | ✅ |
| synthetic_shapes_1920x1080_24f.y4m | checkerboard | payload=1024KiB | 1024 | 0.208 | 0.8091 | 82.2488 | 90.0814 | **57.9279** | 51.1155 | +678.49% | ✅ |
| synthetic_noise_1920x1080_24f.y4m | checkerboard | load=10% | 6 | 0.125 | 0.0082 | 88.5603 | 93.0160 | **52.8009** | 43.7700 | +0.06% | ✅ |
| synthetic_noise_1920x1080_24f.y4m | checkerboard | load=40% | 25 | 0.417 | 0.0098 | 65.6816 | 76.2623 | **46.7853** | 42.9832 | +0.26% | ✅ |
| synthetic_noise_1920x1080_24f.y4m | checkerboard | load=80% | 50 | 0.833 | 0.0098 | 42.8021 | 52.6291 | **43.7726** | 42.9808 | +0.50% | ✅ |
| synthetic_noise_1920x1080_24f.y4m | checkerboard | load=100% | 62 | 1.000 | 0.0102 | 42.8022 | 42.8029 | **42.8029** | 42.8029 | +0.63% | ✅ |

來源 log：
- `src/test/video/synthetic/load_sweep/flat128_log.txt`（sha256 7aa7154705cd，commit bf05120）：synthetic_flat128_1920x1080_24f.y4m，24 幀；容量 coltuc 1514 KiB（0.2492 bpp）；checkerboard 6057 KiB（0.9971 bpp）；來源 74,649,789 B → 無損基準 9,781 B（-99.99%）
- `src/test/video/synthetic/load_sweep/hgrad_log.txt`（sha256 53592401960a，commit bf05120）：synthetic_hgrad_1920x1080_24f.y4m，24 幀；容量 coltuc 1514 KiB（0.2492 bpp）；checkerboard 6057 KiB（0.9971 bpp）；來源 74,649,789 B → 無損基準 229,385 B（-99.69%）
- `src/test/video/synthetic/load_sweep/dgrad_log.txt`（sha256 9cd71e9aa514，commit bf05120）：synthetic_dgrad_1920x1080_24f.y4m，24 幀；容量 coltuc 1512 KiB（0.2489 bpp）；checkerboard 6038 KiB（0.9939 bpp）；來源 74,649,789 B → 無損基準 85,289 B（-99.89%）
- `src/test/video/synthetic/load_sweep/shapes_log.txt`（sha256 a4e7209901c7，commit bf05120）：synthetic_shapes_1920x1080_24f.y4m，24 幀；容量 coltuc 1512 KiB（0.2488 bpp）；checkerboard 6026 KiB（0.9920 bpp）；來源 74,649,789 B → 無損基準 294,261 B（-99.61%）
- `src/test/video/synthetic/load_sweep/noise_log.txt`（sha256 6ba07cbc5c00，commit bf05120）：synthetic_noise_1920x1080_24f.y4m，24 幀；容量 coltuc 0 KiB（0.0000 bpp）；checkerboard 62 KiB（0.0102 bpp）；來源 74,649,789 B → 無損基準 66,954,420 B（-10.31%）
- `src/test/video/synthetic/load_sweep/black_log.txt`（sha256 5981d88641e6，commit bf05120）：synthetic_black_1920x1080_24f.y4m，24 幀；容量 coltuc 0 KiB（0.0000 bpp）；checkerboard 0 KiB（0.0000 bpp）；來源 74,649,789 B → 無損基準 10,240 B（-99.99%）
- `src/test/video/synthetic/load_sweep/white_log.txt`（sha256 a626bd2c9d8b，commit bf05120）：synthetic_white_1920x1080_24f.y4m，24 幀；容量 coltuc 0 KiB（0.0000 bpp）；checkerboard 0 KiB（0.0000 bpp）；來源 74,649,789 B → 無損基準 10,240 B（-99.99%）

# Vendored fonts

Six TrueType sources under `src/`, each family with its `OFL.txt`, all under the SIL Open Font License 1.1.
The build subsets each family against each host's own text and publishes the result as hashed `.woff2`
(a build output, never committed). The licence text and copyright notices stay inside the subset files,
which keep the font's name table.

Source: https://github.com/google/fonts at commit `7085eb89a950e85db5b166b7a58d414544b4140c`,
downloaded 2026-10-07 with Surabhi's yes. Path in that repo, then size in bytes, then SHA-256.

| File in `src/` | Path in google/fonts | Bytes | SHA-256 |
|---|---|---|---|
| `Fraunces[SOFT,WONK,opsz,wght].ttf` | `ofl/fraunces/` | 360440 | `177ff6c0f14e5550a3c624247cd1189611d4eb65d000b14944c63d967958abbb` |
| `Fraunces-Italic[SOFT,WONK,opsz,wght].ttf` | `ofl/fraunces/` | 414904 | `b24448c43702fac4ee856781d461a0dfba8d8e594b6e8e190234b75fed2c0e01` |
| `Inter[opsz,wght].ttf` | `ofl/inter/` | 876576 | `29160a80ff49ddcab2c97711247e08b1fab27a484a329ce8b813d820dc559031` |
| `IBMPlexMono-Regular.ttf` | `ofl/ibmplexmono/` | 135580 | `6a3412f058c7d8dfd9170c41e85ade48e5156ecb89356110ca57a0a27734af46` |
| `IBMPlexMono-Medium.ttf` | `ofl/ibmplexmono/` | 136704 | `a9b4c49bb299e05b5f6c481e7fb5e78943d2793249a0c8874ab574a2d1ea6755` |
| `TiroDevanagariHindi-Regular.ttf` | `ofl/tirodevanagarihindi/` | 423224 | `d2abcb4d352f0bfab91632df5d9c8173882073c182e662fa731a5a738e6681d7` |

| Licence file in `src/` | From | SHA-256 |
|---|---|---|
| `OFL-fraunces.txt` | `ofl/fraunces/OFL.txt` | `bdf4c22802eaf804f998195871c6b8938aac2ac14b2d78a8bd66a6f1eced833b` |
| `OFL-inter.txt` | `ofl/inter/OFL.txt` | `5b9321a4298cfeb6b34354164a1c3afc3db114569984c502b9b35d988fd58c57` |
| `OFL-ibmplexmono.txt` | `ofl/ibmplexmono/OFL.txt` | `7e6b2818edbd8f6a01ae80641cc8f16a51080d08fb4e532be3a0b6f74adb07da` |
| `OFL-tirodevanagarihindi.txt` | `ofl/tirodevanagarihindi/OFL.txt` | `2ed6051706542c5d6d96480318152b17900bb6d4dbadb11d7d5d6464d8b3e0dd` |

The OFL files were renamed on download (each upstream file is called `OFL.txt`) so four can sit in one folder.
`tests/test_assets.py` checks every checksum in this table against the files.

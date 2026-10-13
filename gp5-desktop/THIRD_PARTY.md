# Third-party components

Keep this document, the bundled license texts, and Electron's original notices with
every distributed copy. Exact JavaScript dependency versions are recorded in the
lockfile. Build tools are not end-user runtime dependencies.

| Component | License | Required distribution material |
| --- | --- | --- |
| alphaTab 1.8.4 | Mozilla Public License 2.0 | `LICENSES/alphaTab-MPL-2.0.txt`, `LICENSES/alphaTab-integrated-notices.txt`, and `LICENSES/alphaTab-SOURCE.txt`. |
| Bravura notation font | SIL Open Font License 1.1 | Original copyright notice, reserved font name notice, and OFL text. |
| Noto Sans CJK KR Regular 2.004 | SIL Open Font License 1.1 | `LICENSES/Noto-Sans-CJK-OFL.txt`, including the font's embedded copyright notice. |
| Electron | MIT | Electron's original `LICENSE` from the exact runtime distribution. |
| Chromium and Electron's other bundled components | Component-specific licenses | Preserve the original `LICENSES.chromium.html` and other notices supplied with Electron. |

## alphaTab 1.8.4 corresponding source

GP5 PDF uses the unmodified `@coderline/alphatab` 1.8.4 npm release. The npm release
metadata records source commit `022a45c8e42370f9e12e68949d11eada370da83d`.
The corresponding source, including its license notices, is available at:

- [Pinned alphaTab source tree](https://github.com/CoderLine/alphaTab/tree/022a45c8e42370f9e12e68949d11eada370da83d)
- [Complete corresponding source archive](https://github.com/CoderLine/alphaTab/archive/022a45c8e42370f9e12e68949d11eada370da83d.zip)
- [Exact npm release](https://registry.npmjs.org/@coderline/alphatab/-/alphatab-1.8.4.tgz)

The source is provided under MPL-2.0. No alphaTab source/runtime modifications are
included in this application. Application code calls alphaTab's published APIs.
The upstream `LICENSE.header` integrated-component notices are also retained.

## Bundled Noto font provenance

`assets/fonts/NotoSansCJKkr-Regular.otf` is an unmodified upstream font. Its bytes
were compared with a fresh download from the pinned source below; the SHA-256
values matched.

- Repository commit: `f8d157532fbfaeda587e826d4cd5b21a49186f7c`
- [Exact font source](https://github.com/notofonts/noto-cjk/blob/f8d157532fbfaeda587e826d4cd5b21a49186f7c/Sans/OTF/Korean/NotoSansCJKkr-Regular.otf)
- [Exact upstream OFL text](https://github.com/notofonts/noto-cjk/blob/f8d157532fbfaeda587e826d4cd5b21a49186f7c/Sans/LICENSE)
- SHA-256: `6bcb2a0703aa137e874fc2dffa85f6c21ba9a67fa329e81b8c801663af7e992a`
- Size: 16,433,112 bytes
- Embedded name-table version: `Version 2.004;hotconv 1.0.118;makeotfexe 2.5.65603`
- Embedded copyright: `© 2014-2021 Adobe (http://www.adobe.com/).`
- Embedded trademark: `Noto is a trademark of Google Inc.`

The bundled font was neither subsetted, renamed, converted, nor edited. The
copyright and trademark above are transcribed from its own OpenType name table;
the font's embedded OFL declaration remains intact.

## Distribution terms

alphaTab's file-level MPL does not require unrelated application files to use the
MPL. Minified JavaScript counts as executable form: recipients must still be told
where to obtain the corresponding alphaTab source. If modifying alphaTab in a later
release, provide those changes too and update the corresponding-source notice.
Keep the MPL notice with that source.

Font embedding in the application and generated PDFs is permitted under the OFL.
The fonts retain their own license; PDFs made using them do not become OFL-licensed.
If modifying a font, follow any reserved-font-name restrictions in its license.
Do not omit the font's copyright/OFL text merely because its bytes are embedded in
JavaScript, ASAR, or a data URL.

The macOS archive repackager preserves all original Electron archive entries outside
the explicitly replaced application resource and edited top-level plist, including
Electron/Chromium notices. The build that creates `app.asar` must also include the
alphaTab and font license texts. This document is an attribution index, not a
replacement for those complete texts.

Official sources:

- [alphaTab 1.8.4 license](https://github.com/CoderLine/alphaTab/blob/022a45c8e42370f9e12e68949d11eada370da83d/packages/alphatab/LICENSE)
- [Mozilla MPL distribution FAQ](https://www.mozilla.org/en-US/MPL/2.0/FAQ/)
- [Bravura license](https://github.com/steinbergmedia/bravura/blob/master/LICENSE.txt)
- [Pinned Noto font license](https://github.com/notofonts/noto-cjk/blob/f8d157532fbfaeda587e826d4cd5b21a49186f7c/Sans/LICENSE)
- [Electron license](https://github.com/electron/electron/blob/main/LICENSE)

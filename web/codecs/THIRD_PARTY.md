# Third-party codecs

These files are served unchanged from the same origin as the editor. No CDN or network request is made at runtime.

| Directory | Upstream package | Files | License |
|-----------|------------------|-------|---------|
| `tiff/` | [`tiff.js@1.0.0`](https://www.npmjs.com/package/tiff.js) (LibTIFF, zlib and libjpeg compiled with Emscripten) | `tiff.min.js` | tiff.js/LibTIFF/zlib — `tiff/LICENSE`; IJG libjpeg — `tiff/LICENSE.libjpeg` |
| `webp/` | [`@jsquash/webp@1.5.0`](https://www.npmjs.com/package/@jsquash/webp) (libwebp encoder) | `meta.js`, `codec/enc/webp_enc.js` → `webp_enc.js`, `codec/enc/webp_enc.wasm` → `webp_enc.wasm` | Apache-2.0 — `webp/LICENSE`; libwebp BSD — `webp/LICENSE.libwebp` |

`tiff/worker.js` is WinPaint code that runs the decoder in a dedicated worker with a fixed heap.

SHA-256 of the vendored files (identical to the npm tarballs):

```
f836a31c25978bdd2da43db7bff4912eef501f338f25817c735287e6ddec784d  tiff/tiff.min.js
3d70163a00e6264fc5a8fa7c8f3b1fa21a50a00d910f4d2de3ef1bbd2fdc98ab  webp/meta.js
5fd62301662e37785aec38e38807926f72933d4c8b919018a43faf1b1ca760f6  webp/webp_enc.js
b6085bb6702f144e9dc6016d58d230b34a84976bf0d080b7390b4b4b137d6ab7  webp/webp_enc.wasm
```

# Draft for https://github.com/ophub/amlogic-s9xxx-armbian/issues/new

**Title:**
meson-vdec on 6.18.51-ophub: H.264 hw decode hangs in firmware source-restart loop (search_valid=0); 4K HEVC fails with CMA allocation failure (S905X2 / G12A)

---

## Environment

- Kernel: `Linux armbian 6.18.51-ophub #1 SMP PREEMPT_DYNAMIC Mon Sep 14 02:05:42 UTC 2026 aarch64`
- Board: X96 Max (Amlogic **S905X2**, meson-g12a), Armbian (armbian/build fc4623b), `BOARD="S905x2"`, `LINUXFAMILY="amlogic"`
- Decoder: `meson-vdec ff620000.video-decoder` (frame-based multi-instance, `drivers/staging/media/meson/vdec`, ophub/linux-6.18.y commit `fb220895` "add frame-based multi-instance decoding")
- Firmware dir `/lib/firmware/meson/vdec`: `g12a_h264_multi.bin` = 28672 bytes (exact `H264_MULTI_FW_SIZE`), `g12a_hevc_mmu_multi.bin` = 40960 bytes installed
- Clients: mpv 0.35.0 (v4l2m2m), ffmpeg 7.0.2 static (`h264_v4l2m2m`), Debian bookworm userland

---

## Bug 1: H.264 hardware decoding never produces a frame — infinite state loop

**Repro:**
```
mpv --no-config --vo=null --hwdec=v4l2m2m-copy --hwdec-codecs=h264 any-h264-file.mp4
# or: ffmpeg -c:v h264_v4l2m2m -i test_h264.mp4 -f null -
```

**Expected:** H.264 decodes via hardware.

**Actual:** playback hangs forever (no frame is ever output; process must be killed). Kernel log spams the same 3-line cycle indefinitely — **596 log lines in 6 seconds**:

```
meson-vdec ff620000.video-decoder: H.264 source resume: active=1 configuring=1 status=2 changed=1 stopped=0 streamon_cap=1 config_valid=1 capture=11 allocated=20
meson-vdec ff620000.video-decoder: H.264 hardware start pending source resume: status=2 streamon_cap=1 input=1 search_valid=0
meson-vdec ff620000.video-decoder: H.264 firmware source restart: status=2 streamon_cap=1 input=1 search_valid=0
```

**Notes:**
- The firmware handshake itself completes (`config_valid=1`, `capture=11 allocated=20`), but the state machine immediately re-enters `hardware start pending` with `search_valid=0` and restarts the firmware source — a livelock.
- Reproduces with both mpv and a stock ffmpeg 7.0.2 client (so not a client-side issue).
- Same client/file decodes fine in software (libavcodec sw h264).
- `g12a_h264_multi.bin` size = 28672 = `H264_MULTI_FW_SIZE` constant in the driver, so it does not look like a wrong-size firmware problem.
- **HEVC and VP9 work fine on the same box with the same driver**: HEVC 1080p sustained 18.8x realtime (ffmpeg7 benchmark, 300/300 frames), VP9 1080p 17.3x realtime, mpv plays both with v4l2m2m-copy without errors.

---

## Bug 2: 4K HEVC: CMA dma-alloc fails, session aborts, client hangs

**Repro:**
```
mpv --no-config --vo=null --hwdec=v4l2m2m-copy --hwdec-codecs=hevc 4k-hevc-file.mp4
```
(3840x2160 HEVC, any profile; test clip generated with x265)

**Actual:** no frame is ever decoded; the client waits forever (had to be killed by timeout). Kernel log:

```
meson-vdec ff620000.video-decoder: dma alloc of size 8323072 failed
cma: __cma_alloc: linux,cma: alloc failed, req-size: 2032 pages, ret: -16
cma: number of available pages: => 1096 free of 65536 total pages
...
meson-vdec ff620000.video-decoder: Unrecognized dec_status: 00000025
meson-vdec ff620000.video-decoder: Aborting decoding session!
```

**Notes:**
- `CmaTotal = 262144 kB` (256 MB); during the failure only ~4.3 MB (1096 pages) remained, i.e. the DPB allocation for 4K exhausts/fragments the pool.
- 4K **VP9** decodes fine via hardware on the same box (mpv, DROP=0), 4K H.264 works in software (DROP=0), 1080p HEVC via hardware works — only 4K HEVC hits this.
- Expected: either decode (the SoC is rated for 4Kp60 HEVC) or a clean error to userspace instead of an indefinite hang.

---

## Related observation (may share the root cause)

MPEG-2 hardware decoding also fails to run — one frame may pass, then the driver prints repeatedly:
```
meson-vdec ...: Buffer N done but it doesn't exist in m2m_ctx
```
(single-instance firmware `g12a_mpeg12` path; log from an earlier session).

---

## Summary

- HEVC (≤1080p) and VP9 (≤4K) hardware decoding work and are fast — thanks for the active vdec work!
- H.264 (the most common codec in the wild) is completely non-functional due to the state-machine livelock above.
- 4K HEVC needs either a larger/less-fragmented CMA pool or DPB allocation tuning; at minimum the failure should surface to userspace instead of hanging.

Happy to run further tests or provide full logs.

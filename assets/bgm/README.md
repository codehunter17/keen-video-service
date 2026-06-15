# Background music tracks

Drop **royalty-free** `.mp3` tracks here, named by `bgm_style`. The render
engine ducks the matching track under the voiceover at `bgm_volume` (default
0.12). A request with `bgm_style: "chill"` uses `chill.mp3`; if the file is
missing, the video renders with voiceover only (the job never fails for it).

Examples:
```
assets/bgm/chill.mp3
assets/bgm/upbeat.mp3
assets/bgm/calm.mp3
```

Sources for royalty-free music (license each track before shipping): Pixabay
Music, Free Music Archive (CC), YouTube Audio Library, Uppbeat. Do NOT add
copyrighted tracks — this folder is committed/deployed with the service.

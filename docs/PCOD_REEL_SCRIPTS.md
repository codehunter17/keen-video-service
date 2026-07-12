# PCOD/Hormonal Hinglish reel scripts — ready to render

Five validation-ready scripts for NutriMama's **PCOD-first go-to-market wedge**
(see `KNOWLEDGE_GRAPH.md` §8/§10). Each renders to a ~30–45s 9:16 reel through
this service. They are written in Devanagari-heavy Hinglish so the Hindi TTS
voice (`hi-IN-SwaraNeural`) and the script-aware caption fonts do their best
work, and every script ends with the same informational disclaimer + CTA.

**Content rules baked into these scripts (keep them in new ones):**

- Myth-buster / question hooks in the first sentence — the first 3 seconds
  decide the scroll.
- Management/support language only — never "cure". No medicine advice, no
  "stop your pills". This is the liability line; do not cross it.
- Desi foods only (ragi, chana, palak, methi…) — that's the differentiator.
- Short sentences: each sentence = one scene = one stock clip, so 5–8
  sentences is the sweet spot.

## How to render one

```bash
BASE=https://keenhunter-keen-video-service.hf.space
KEY=<SERVICE_API_KEY>

curl -sX POST "$BASE/api/v1/generate-video" \
  -H "Content-Type: application/json" -H "X-Keen-Key: $KEY" \
  -d @- <<'JSON'
{"topic_or_script": "<paste one script below as a single line>",
 "voice_id": "hi-IN-SwaraNeural", "bgm_style": "none"}
JSON
# → poll the returned status_url until state=done, then share output_url.
```

> Tip: with `HF_OUTPUT_REPO` configured on the Space, `output_url` is a durable
> link that survives Space restarts — safe to post in WhatsApp groups.

---

## Reel 1 — "PCOD mein chawal band?" (myth-buster)

> PCOD में चावल बिल्कुल बंद? ये सबसे बड़ा myth है। सच ये है कि मात्रा और combination मायने रखता है। सादा चावल के साथ दाल और सब्ज़ी मिलाओ, तो blood sugar धीरे बढ़ता है। रात में हल्का खाना, दिन में भरपूर protein। खाना दुश्मन नहीं है, सही तरीका दोस्त है। ये जानकारी है, इलाज नहीं — अपने doctor से ज़रूर मिलें। अपनी hormone report समझने के लिए NutriMama पर आएं।

## Reel 2 — "PCOD kya hai, 30 second mein"

> हर पाँच में से एक लड़की को PCOD छू रहा है। Periods late, चेहरे पर दाने, वजन बढ़ना — ये सब hormones के signal हैं। PCOD कोई शर्म की बात नहीं, एक hormonal imbalance है। सही खाना, नींद और movement से इसे manage किया जा सकता है। शुरुआत होती है अपने शरीर को समझने से। ये जानकारी है, इलाज नहीं — doctor से ज़रूर मिलें। NutriMama पर अपनी report upload करो और अपनी थाली से शुरुआत करो।

## Reel 3 — "5 desi foods for hormones"

> Hormones के लिए महंगे supplements नहीं, अपनी रसोई देखो। पहला, चना — protein का देसी powerhouse। दूसरा, पालक — iron और folate का साथी। तीसरा, मेथी दाना — blood sugar का दोस्त। चौथा, रागी — refined आटे का smart बदला। पाँचवाँ, दही — पेट और hormones दोनों खुश। ये जानकारी है, इलाज नहीं — doctor से ज़रूर मिलें। अपना हफ़्ते का desi diet plan NutriMama पर पाओ।

## Reel 4 — "Crash diet ka sach" (PCOD + weight)

> PCOD में वजन घटाने के लिए भूखा रहना? उल्टा पड़ेगा। Crash diet से hormones और बिगड़ते हैं, और वजन वापस आ जाता है। शरीर को सज़ा नहीं, सही fuel चाहिए। धीरे-धीरे बदलाव — हर खाने में protein, fiber और थोड़ा सा patience। तीन महीने का सही खाना, तीन हफ़्ते की भुखमरी से बेहतर है। ये जानकारी है, इलाज नहीं — doctor से ज़रूर मिलें। अपना personalized plan NutriMama पर बनाओ।

## Reel 5 — "Report ke woh 4 naam" (report literacy)

> PCOD की report में डरावने नाम, आसान भाषा में समझो। LH और FSH — ये periods की timing के मालिक हैं। Insulin — ज़्यादा हो तो वजन और cravings बढ़ाता है। Thyroid — थकान और mood का बटन। ये numbers डराने के लिए नहीं, राह दिखाने के लिए हैं। Report को समझो, फिर doctor से सही सवाल पूछो। ये जानकारी है, इलाज नहीं। अपनी report NutriMama पर upload करो — हम उसे आपकी भाषा में समझाते हैं।

---

## What to measure per reel (validation, not vanity)

| Metric | Question it answers |
|---|---|
| 3-second holds / views | Does the hook stop the scroll? |
| Saves + shares | Is it useful enough to keep or send to a friend? |
| Profile/link taps | Does the CTA move anyone toward the app? |
| Replies/DMs | What words do real users use? (steal them for the next script) |

Run all five, keep the top two styles, write the next five in that style.

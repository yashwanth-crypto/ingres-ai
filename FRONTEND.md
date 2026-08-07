# The frontend, in detail

Twelve source files, 1,504 lines, no component library. What each one does, the
decisions behind them, and the bugs that shaped them.

For the pipeline behind it see [WALKTHROUGH.md](WALKTHROUGH.md); for the
file-by-file backend view see [ARCHITECTURE.md](ARCHITECTURE.md).

---

## 1. The stack, and what is deliberately absent

| | Version | Why |
|---|---|---|
| React | 18.3.1 | |
| Vite | 5.4.21 | Dev server proxies `/api`, so the browser makes no cross-origin request |
| Tailwind | 3.4.17 | With a custom theme, not the default palette |
| Recharts | 2.13.3 | The trend chart only |
| Leaflet + react-leaflet | 1.9.4 / 4.2.1 | The district map |

**Absent on purpose:** no component library, no state manager, no router, no
form library, no icon package, no webfont.

State is four `useState` calls in one component. Routing would be a single
route. Icons are hand-authored inline SVG — six paths in total. Every dependency
avoided is a dependency that cannot break on demo day.

Production build:

```
index.html      0.42 kB   gzip   0.30 kB
index.css      32.93 kB   gzip  10.62 kB
index.js      728.92 kB   gzip 210.05 kB
```

Recharts and Leaflet are essentially all of that JavaScript. It only matters if
this is ever deployed; locally it is served from disk.

---

## 2. Every file

| File | Lines | Job |
|---|---|---|
| `main.jsx` | 12 | Mount, and the Leaflet stylesheet import |
| `App.jsx` | 68 | Shell, wordmark, live health indicator |
| `api.js` | 85 | `sendMessage` · `streamMessage` · `getHealth` |
| `categories.js` | 27 | CGWB category colours, shared |
| `index.css` | 125 | Keyframes, all disabled under reduced motion |
| `components/ChatWindow.jsx` | 122 | State, submission, scroll pinning |
| `components/AquiferHero.jsx` | 246 | The landing page |
| `components/PipelineProgress.jsx` | 126 | What the pipeline is doing, live |
| `components/MessageBubble.jsx` | 154 | One message, and the verification footer |
| `components/TrendChart.jsx` | 292 | Depth over time, drawn as a cross-section |
| `components/RankChart.jsx` | 121 | Districts side by side |
| `components/MapView.jsx` | 126 | Districts on a map |

---

## 3. The design system

Defined in `tailwind.config.js`, and it is short on purpose.

```
depth-50   #eef6f7      depth-600  #1d6473
depth-100  #d3e7ea      depth-700  #164e5b
                        depth-900  #0b2c34
```

Deep water blues against Tailwind's warm **stone** greys — a dry-earth neutral
rather than the default cool grey. The strata browns in the landing page
(`#c9b79a` → `#8a755a`) come from the same idea: everything on screen is either
water or the ground above it.

### Type: system stacks only

```js
sans:    ["Segoe UI", "system-ui", "-apple-system", "sans-serif"]
display: ["Georgia", "Cambria", "Times New Roman", "serif"]
```

**No webfont, and that is a decision rather than an omission.** The demo may run
with no internet. A linked webfont would fail silently and fall back to
something worse than a deliberately chosen system stack. Georgia for headings
gives the interface a documentary rather than a product feel, which suits a page
of government monitoring data.

### CGWB categories, in one place

```js
"over-exploited": "#b91c1c"    critical:        "#ea580c"
"semi-critical":  "#d97706"    safe:            "#15803d"
no category:      "#78716c"
```

These live in `categories.js` because the map and the bar chart often appear in
the same answer. A district shown red on one and orange on the other reads as
two different findings.

---

## 4. The landing page — `AquiferHero.jsx`

An animated cross-section of an aquifer: sky, four strata bands, scattered
grain specks, three wells, a depth scale at 0 / 15 / 30 / 45 m, and a saturated
zone that **sinks and resets on a 14-second loop**.

The whole product is about depth below ground, and nothing else in the interface
showed that physically.

**All inline SVG.** No image files, no icon font, nothing to fetch — it renders
with the network unplugged. The "soil texture" is 90 circles placed by
`(i * 137) % 800`, which is cheaper and more reliable than a texture file.

Four counting stats — **1,607 stations · 36,879 readings · 28 years · 20 of 23
over-exploited** — animate up on mount, and four tagged prompt cards seed the
first question.

> **A bug worth keeping.** The count-up uses `requestAnimationFrame`, which is
> paused in a hidden or backgrounded tab — so the headline figures would have
> been stuck at zero for anyone who opened the app in a background tab. A
> `setTimeout` snaps them to the real value regardless, because timers keep
> running when frames do not.

---

## 5. The conversation — `ChatWindow.jsx`

Four pieces of state: `messages`, `input`, `busy`, `stages`. That is the whole
store.

**Bottom-anchored list.** `flex min-h-full flex-col justify-end` — a short
conversation sits just above the input instead of stranding it at the top of an
empty page.

**Scroll pinning** sets `scrollTop` directly rather than
`scrollIntoView({ behavior: "smooth" })`. Smooth scrolling is animation-driven
and does nothing in a backgrounded tab, which would leave the newest answer
below the fold. It re-pins at 260 ms and 900 ms as well, because charts and map
tiles lay out *after* the effect runs and grow the message.

---

## 6. Live progress — `PipelineProgress.jsx`

Answering takes 3 to 15 seconds. That used to be three bouncing dots.

`api.js` reads the server-sent event stream with `fetch` + `ReadableStream`,
buffering partial events because a network chunk can split one anywhere:

```js
const events = buffer.split("\n\n");
buffer = events.pop() ?? "";      // keep the incomplete tail
```

`foldStage()` is a pure reducer that collapses each announcement into its
result, so nine events read as four lines:

```
✓ Understood — projection · Ludhiana
✓ Retrieved — 22 stations reporting on 2024-01-01; 75 station trends over 15 years
✓ Projected — 20.1 years to 30 m, at 0.504 m/year
✓ Verified — every figure traced to 3 sources
```

Settled lines get a check; the active one gets the animated dots. The list
carries `aria-live="polite"` so a screen reader hears each step.

`streamMessage` falls back to the plain endpoint if the browser gives no
readable stream — a missing feature costs the progress display, not the answer.

---

## 7. The message, and its footer — `MessageBubble.jsx`

Verification is the whole claim of the system, and the interface used to mention
it **only when it failed**. An answer that passed every check looked exactly
like an answer from any chatbot.

The footer now states three things: that every figure was checked, which source
answered (*Monitoring database* or *CGWB report*), and the citations behind it.
Icons are inline SVG so nothing has to load for the state to be legible.

An out-of-scope reply carries no verdict and nothing to cite, so it gets **no
footer at all** rather than an empty grey band under a one-line refusal.

---

## 8. The trend chart — `TrendChart.jsx`

The largest component, and the one with the most decisions in it.

**The Y axis is inverted.** `water_level_m` is depth *below ground*, so a larger
number means deeper water, which is worse. Plotting it downward makes a falling
line mean a falling water table — which is what people expect to see.

**Ground is filled above the line**, in AquiferHero's strata tones. The chart
and the landing page describe the same physical thing, so they look like it: the
blue line is visibly the boundary between dry ground and water.

**The projection** — for "how many years until…" questions — is drawn dashed
into a shaded `PROJECTED` region, ending on a marked crossing of the reference
depth. It is anchored on the figure the answer *quotes*, not snapped onto the
history line, because the chart must show the number in the prose.

> **Four defects fixed here, all found by measuring the rendered output rather
> than reading the code:**
>
> - The rotated Y-axis label was placed at `x = -3` — outside the SVG, rendering
>   as a sliver at the left edge.
> - Ticks came out at **13 / 21 / 34** — three of them, unevenly spaced. Depths
>   are read by comparison, so the steps must be even. Now 10 / 15 / 20 / 25 / 30.
> - The "30 m reference depth" label sat on top of the projection's final
>   approach.
> - Recharts drives `stroke-dasharray` to animate a line drawing itself, which
>   would have eaten the dash that distinguishes a projection from a
>   measurement. The projection line never animates.

---

## 9. The ranked bars — `RankChart.jsx`

**Plain CSS grid, not Recharts.** A labelled horizontal bar is laid out better
by a three-column grid than by a chart library, and the bundle is already
carrying Recharts and Leaflet.

Bars are worst-first, coloured by CGWB category, with the district that answers
the question at full opacity and the rest at 0.55 — a superlative's answer is
one bar among eight that otherwise look alike.

Long district names — **Sahibzada Ajit Singh Nagar**, **Shahid Bhagat Singh
Nagar** — wrap to two lines rather than truncate. Clipping names mid-word in a
chart about which district is worst defeats the point of naming them.

On a phone the columns narrow and the station counts hide, because at 375 px the
bar track was 70 px against 192 px of text — putting the least of the chart into
the data. It is now 134 px.

> **The animation was rewritten after it stranded the chart.** The first version
> transitioned `width` up from zero on a state flag: the inline width read
> `100%` while the computed width stayed `0px`, so a chart that never received
> animation frames rendered *empty*. Now the width is always final in the markup
> and only a `transform` animates. **Nothing load-bearing is animated.**

---

## 10. The map — `MapView.jsx`

Leaflet with OpenStreetMap tiles, one circle marker per district at the mean
coordinate of its monitoring stations, coloured by category, with a popup.

It **fits bounds to the actual points** rather than trusting a fixed zoom, and
**names any district it could not plot** instead of quietly showing fewer pins —
Malerkotla has a CGWB category and no stations.

> **The two bugs here are the best lesson in the project.**
>
> Leaflet's stylesheet is imported from `main.jsx`, not `index.css`, because a
> CSS `@import` must precede every other rule — placing it after the `@tailwind`
> directives got it **silently dropped**. Without it, tiles are `position:
> static`, and the map draws itself outside its own frame.
>
> Separately, Leaflet measures its container once, at mount — and here the
> container is still settling, because the message list grows as the answer
> renders. It computed its pixel origin from the wrong size and **drew Punjab's
> tiles as though they were Gujarat.** `invalidateSize()` at 80, 350 and 900 ms
> fixes it.
>
> Every DOM check passed the whole time. `.leaflet-container` was present,
> `.leaflet-tile-loaded` was present. **Counting elements is not verification** —
> only the computed styles revealed it.

---

## 11. Motion and accessibility

Every keyframe in `index.css` is decorative, and all of them are disabled in one
block:

```css
@media (prefers-reduced-motion: reduce) {
  .water-table, .well-pulse, .fade-up,
  .message-in, .bar-grow, .dot { animation: none !important; }
}
```

**Recharts animates in JavaScript, so that rule cannot reach it.** The trend
chart reads `matchMedia("(prefers-reduced-motion: reduce)")` directly and passes
`isAnimationActive={false}`.

Also: the progress list is `aria-live="polite"`, the hero SVG carries
`role="img"` and an `aria-label`, decorative icons are `aria-hidden`, and no
page scrolls sideways at 375 px.

---

## 12. Talking points, if you are asked about the frontend

- **Three visualisations, chosen by the intent — not by the model.** The model
  has "needs a chart" flags and it left them false on questions that plainly
  wanted one, so the decision is a rule.
- **The inverted axis** is the most explainable design decision you have, and it
  comes straight from the domain.
- **The map names what it cannot show.** That single footnote says more about
  the project's values than any feature list.
- **The Leaflet story** — "every DOM check passed while the map rendered Gujarat"
  — is a good answer to *"how do you test the frontend?"*
- It runs **fully offline** apart from map tiles: system fonts, inline SVG, no
  CDN, no webfont, no icon package.

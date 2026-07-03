# Chunked Progress Bar

An Anki add-on that splits your review session into fixed-size **chunks** and shows your progress on two linked bars while you review:

- **Chunk bar** — one tile per chunk (e.g. per 10 cards). Completed chunks are coloured by how well you answered the cards inside them, the chunk you are in is highlighted, and upcoming chunks stay dimmed.
- **Card bar** — a zoomed-in view of the current chunk, one tile per card, coloured by the answer you gave (Again / Hard / Good / Easy).

Reviewing a big backlog feels much lighter when it's "3 chunks left" instead of "137 cards left".

## Features

### Chunk evaluation
When a chunk is completed, the add-on averages the answers inside it (each of Again / Hard / Good / Easy has a configurable weight) and colours the tile based on which interval the average falls into. Intervals are fully editable: boundaries, open/closed brackets, and which ones are enabled. Borderline intervals use a striped two-colour pattern.

### FSRS integration
Instead of tuning intervals by hand, you can generate them from a **desired retention** value: chunks that meet your retention target are coloured as passing, chunks below it as failing. Optionally the add-on can:

- recalculate the intervals automatically when you change the chunk size, and
- fetch the desired retention of the deck you select (averaged over its subdecks) and adapt the colouring to it.

### Perfect chunks
Chunks where every card was answered with a passing grade can be highlighted with a special colour. You can choose whether Hard counts as perfect or whether only Good/Easy do.

### Session tracking
- Progress is rebuilt from today's review log when you enter the reviewer, so it survives restarts, deck switches and syncs.
- Failed cards can either be acknowledged (the bar grows to include the extra reviews, with the excess highlighted) or ignored.
- Burying and suspending is detected — including from the menus — and can be acknowledged or ignored.
- Undo can either roll the bar back or mark the undone answer in its own colour.
- New cards can optionally be counted twice, matching decks where a new card comes back once more the same day.

### Text, numbers and timers
Each bar can independently show:

- a number or percentage on every tile (counting done or remaining, chunk-wise or card-wise, absolute or relative to the chunk),
- a large centred number or percentage for the whole bar (e.g. `374/1327` or `62.50%`),
- per-chunk and per-card **timers**, including a live timer for the current card/chunk.

Every text element has its own colour, bold and outline settings. Text can hide itself automatically when tiles get too small, and the centred text gets out of the way while you **hover** over the bars so you can read the tile labels underneath.

### Layout
Each bar can be placed at the top or bottom of the main window (or hidden), in any stacking order. All colours are customisable, including the ones for buried, suspended and undone cards.

## Settings

Open **Tools → Progress Bar Settings**, or simply **double-click either bar**. All changes preview live while you review.

## Installation

In Anki, go to **Tools → Add-ons → Get Add-ons…**, paste this code and restart Anki:

```
1724662218
```

You can also find it on [AnkiWeb](https://ankiweb.net/shared/info/1724662218).

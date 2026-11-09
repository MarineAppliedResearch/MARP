# Habitat dataset viewer

A one-off tool for looking at the habitat classification datasets built during
MarineAppliedResearch/MARP_API#287: the frames cut from CAMPA ROV video, each labelled with
the substrates on it (Rock, Mud, Sand, Cobble, Boulder). It replaces reading the label file
by hand.

It is a stopgap. The intended home for this is the Mosaic
(MarineAppliedResearch/MARP_API#342, *View habitat classification datasets in the Mosaic*).
Whether this tool, or anything in it, becomes part of MARP is still to be decided. Until
then it lives here and nothing depends on it.

## Running it

It needs Node and nothing else: no packages, no database, no Jellyfin.

```
node legacy/habitat-dataset-viewer/serve.js <experiment folder> [port]
```

The experiment folder is `.marp/habitat/experiment` in a MARP_API checkout of branch
`287-habitat-classification`, after the pipeline there has built a dataset (its
`README.md` has the steps). The port defaults to 8287. Open the address it prints. It
listens on this machine only.

## What it shows

- **Counts**: frames per CAMPA year, split into training, tuning and test dives (test dives
  are never trained on), and how many frames show each substrate. Both follow the filters.
- **Filters**: year, split, substrate, and dive and line. A substrate can be asked for in
  three ways: present with or without others, present on its own, or absent.
- **Grid**: the frames in dive order and then along the video, with their labels. A frame
  the download has not reached yet says so.
- **Timeline**: with one dive and line chosen, its labels laid out along the video, the way
  the annotators recorded them. Each frame stands for the 10 s around it, so a blank stretch
  is one with no usable frame. Clicking the timeline opens the nearest frame.
- **Full frame**: click any frame. The arrow keys step through the filtered list. It
  darkens the top quarter, the ROV's overlay, which the trainer cuts off so the model cannot
  learn a dive from its date and depth, and outlines the bottom-middle crop that one of the
  training runs uses.

## How it works

Two files:

- `serve.js` serves the page, the list of datasets, the dataset CSVs and the pictures,
  all read straight from the experiment folder. A dataset is any CSV there whose first
  column is `image`, so `dataset.csv`, `dataset_full.csv` and the others all appear in the
  page's dataset list. It serves nothing else from that folder, and refuses a path that
  climbs out of it.
- `index.html` does everything else in the browser: it reads the chosen CSV, filters it,
  and draws the counts, grid, timeline and full frame. No libraries.

The CSV columns it reads are the pipeline's: `image`, `split`, `project`, `dive`, `line`,
`session`, `video`, `seconds_into_video`, and one 0/1 column per substrate. The crop
outlines are copied from `train.py` (`OVERLAY_ROWS` and `CROPS`) and would need changing
by hand if those did.

`dataset.csv` points at the trickplay thumbnails under `frames/`, which only exist on a
machine that ran the thumbnail step, so on most machines only `dataset_full.csv` shows
pictures.

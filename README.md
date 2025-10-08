# Market Map

This repository contains a single-page Leaflet web app that visualizes the embedded dataset of company locations. The original CSV (``Location List Oct 2025.csv``) has been processed to add pseudo-geographic coordinates for each row so the points can be displayed on the map without relying on an external geocoder.

## Files

- ``index.html`` – self-contained interactive map with controls to filter by line of business, color-coded markers by region, and a download button for the enriched CSV. The full dataset is embedded directly in this file so it can be used standalone.
- ``Location List Oct 2025 with locations.csv`` – processed CSV that adds ``Latitude``, ``Longitude``, and ``Location`` columns computed from the city/state pairing.
- ``Location List Oct 2025.csv`` – original dataset provided in the repository.

## Usage

Open ``index.html`` in any modern browser. The map loads immediately, letting you filter by line of business or download the updated CSV. No build steps or external tooling are required.

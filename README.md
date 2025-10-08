# Market Map

This repository contains a single-page Leaflet web app that visualizes the embedded dataset of company locations. The original CSV (``Location List Oct 2025.csv``) has been processed to add pseudo-geographic coordinates for each row so the points can be displayed on the map without relying on an external geocoder.

## Files

- ``index.html`` – self-contained interactive map with controls to filter by line of business, color-coded markers by region, and a download button for the enriched CSV.
- ``Location List Oct 2025 with locations.csv`` – processed CSV that adds ``Latitude``, ``Longitude``, and ``Location`` columns produced by geocoding each address.
- ``data_with_locations.json`` – JSON export of the enriched dataset used by the HTML page.
- ``update_locations.py`` – helper script that regenerates the geocoded outputs using the US Census batch geocoder with OpenStreetMap fallbacks.
- ``Location List Oct 2025.csv`` – original dataset provided in the repository.

## Usage

Open ``index.html`` in any modern browser. The map loads immediately, letting you filter by line of business or download the updated CSV. No build steps or external tooling are required.

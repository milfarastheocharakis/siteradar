# SiteRadar

Find local businesses in Greece that have no website, only a Facebook or booking page, or a website that is broken, slow or not made for phones. It is built for selling websites to local businesses, starting with Heraklion and Rethymno in Crete.

**Open it:** https://milfarastheocharakis.github.io/siteradar/

## How to use it

1. Pick the municipality, type an address (in Greek or English letters) and a radius, and press **Search**.
2. The list puts the best leads first. Click a business to see why it scored, its phone and address, and links to Google Maps.
3. Mark leads, write notes and set follow-up dates. They show under **My leads**, and the **Follow-up due** filter is your call list.
4. Tap ✓ on a row when a business **accepted work**, or ✗ when it **didn't want a site**. The next time you search the same area, the businesses you marked (and any marked **Has a good site**) are left out, so the list only shows the ones still to work on. **Show them** brings them back, and they always stay under **My leads**.
5. Press **Check websites** to test the businesses' websites with Google's free PageSpeed check. This needs your own free Google key (see below).
6. Export the list to Excel or CSV.

After a search you can also load every business in the whole municipality.

## Google key for the website check

The website check uses Google PageSpeed Insights. It is free, but it needs a key:

1. Open the [PageSpeed Insights API page](https://console.cloud.google.com/apis/library/pagespeedonline.googleapis.com), sign in, pick or create a project, and press **Enable**.
2. Open [Credentials](https://console.cloud.google.com/apis/credentials), press **Create credentials**, then **API key**.
3. In SiteRadar, press the gear button and paste the key.

Optional: limit the key to the PageSpeed Insights API, and to the website `https://milfarastheocharakis.github.io/*`. With the website limit, the key won't work in a downloaded copy of the file.

## Where the data comes from

- Businesses: [OpenStreetMap](https://www.openstreetmap.org/copyright) (© OpenStreetMap contributors, ODbL), loaded live through the Overpass API. OpenStreetMap misses some businesses and websites, so check on Google before you call.
- Addresses: Nominatim, with Photon as a backup.
- Map: OpenStreetMap's own map tiles (free, no key). In dark mode the app darkens them.
- Website checks: Google PageSpeed Insights.

## Privacy

SiteRadar is a single HTML file with no server of its own. Your notes, statuses, follow-up dates, website checks and Google key are saved only in your own browser. Nothing is uploaded, so they don't move between your computer and your phone.

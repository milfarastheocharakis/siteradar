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

## What it lists

Only companies. Public offices and municipal facilities, state schools and universities, churches and monasteries, clubs and associations, banks and ATMs, ports and airports are left out. They are spotted by their kind of place, by their name (for example "Κέντρο Υγείας", "ΚΕΠ", "Ιερός Ναός" or "2ο ΓΕΛ") or by a public website such as gov.gr or sch.gr. Private schools, tutoring centres, private nurseries, church-supply shops and the like stay. The rules are the `NOT_COMPANY`, `STILL_COMPANY` and `NOT_COMPANY_SITES` lists in `index.html`, and the weekly data build reads them from there too.

- A page on a booking site, a directory or town portal, a food-ordering site, Facebook or Instagram is not the business's own website, so that business is still a lead. An email address given as the website counts as no website.
- Chains and brands are hidden while **Hide chains** is on. Besides known brands, this covers one website shared by the same business name in several towns of Crete (a supermarket chain, for example) and holiday homes let through a rental company such as Belvilla.
- The same distinctive name listed twice within 150 m is shown once.

## Google key for the website check

The website check uses Google PageSpeed Insights. It is free, but it needs a key:

1. Open the [PageSpeed Insights API page](https://console.cloud.google.com/apis/library/pagespeedonline.googleapis.com), sign in, pick or create a project, and press **Enable**.
2. Open [Credentials](https://console.cloud.google.com/apis/credentials), press **Create credentials**, then **API key**.
3. In SiteRadar, press the gear button and paste the key.

Optional: limit the key to the PageSpeed Insights API, and to the website `https://milfarastheocharakis.github.io/*`. With the website limit, the key won't work in a downloaded copy of the file.

## Where the data comes from

- Businesses: [OpenStreetMap](https://www.openstreetmap.org/copyright) (© OpenStreetMap contributors, ODbL) and, in Crete, [Overture Maps](https://docs.overturemaps.org/guides/places/) (Overture Maps Foundation, data from Meta, Microsoft and others, [CDLA Permissive 2.0](https://cdla.dev/permissive-2-0/)). Both miss some businesses and websites, so check on Google before you call.
  - Crete is stored in `data/` next to the app, so searches there are instant and don't depend on the busy public map-data servers. A GitHub Actions workflow (`.github/workflows/data.yml`, free for a public repo) rebuilds it every Monday from the [Geofabrik](https://download.geofabrik.de/europe/greece.html) extract of Greece and the latest monthly Overture Maps release. The search summary shows the date of each. To rebuild now: Actions → Refresh business data → Run workflow.
  - Overture's places come mostly from Facebook business pages, so they hold many small businesses OpenStreetMap lacks. When both have the same business, the OpenStreetMap entry stays and takes the website, social pages and phone it was missing from Overture. Each business's details say where it came from. Places from Foursquare are left out, because their licence would need extra files next to the data.
  - `data/LICENSE.txt` says where the data comes from and holds the Overture licence, which must travel with the data.
  - Outside Crete, the app asks the Overpass API live (three public servers; if one is slow, it asks the next). That is OpenStreetMap only.
- Addresses: Nominatim, with Photon as a backup.
- Map: OpenStreetMap's own map tiles (free, no key). In dark mode the app darkens them.
- Website checks: Google PageSpeed Insights.

## Privacy

SiteRadar is a single HTML file plus its stored business data, with no server of its own. Your notes, statuses, follow-up dates, website checks and Google key are saved only in your own browser. Nothing is uploaded, so they don't move between your computer and your phone.

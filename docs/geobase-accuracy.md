# The cities other APIs lose are here

GeoDB Cities (50,222 subscribers) has years of user reports in its own
RapidAPI Discussions about places that are wrong, missing, or deleted.
GeoBase Cities was built from the same public upstream (GeoNames, CC BY)
and its launch test set is those exact places. Every result below was
returned by the live GeoBase service on 2026-10-28.

| Place users reported broken | What GeoBase returns |
| --- | --- |
| Rome "deleted" (users asked for its return by name) | id 3169070, capital of Italy, region Lazio, population 2,318,895 |
| Surrey, BC "missing" | id 6159905, region British Columbia, population 568,322 |
| Cluj-Napoca "deleted" | id 681290, region Cluj County, population 286,598 |
| Sao Paulo "findable only by ID, not by name" | Found by plain name search for "Sao Paulo" (accents folded), id 3448439, population 12,400,232 |
| Sevastopol "returned in the Buryatia region" | Region: Sevastopol City, its own admin region |
| Sterling, VA requests | id 4787534, region Virginia, population 27,822 |

Coverage, stated honestly: 34,191 populated places (population 15,000+
and all capitals), 3,865 regions, 252 countries, refreshed from the
GeoNames daily dump at service start. Smaller places arrive with the v2
dataset expansion, and the correction pipeline reviews reported places
against Wikidata instead of leaving threads unanswered.

Data: GeoNames contributors, CC BY 4.0 (download.geonames.org).

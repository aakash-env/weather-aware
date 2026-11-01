# Loom walkthrough (~7 minutes)

Record against a running app. Use a heavy load (about 42,000 lb) and a trip long enough to show more than one corridor, such as Chicago to Denver. Keep a second tab or be ready to switch to Los Angeles to New York for the slider.

1. **What it solves (0:30).** A driver enters origin, destination, departure, and load. The app compares real driving routes on weather at the truck's estimated arrival, not on the weather at departure. Stack: React, MapLibre, Django.

2. **Recommendation (1:30).** Submit the trip. Point at three route cards: distance, duration, arrival, Severe / High / Moderate miles, the stacked bar, and the Recommended badge. Read the `why` sentence so the order is visible: Severe miles, then High miles, then average risk, then time.

3. **A checkpoint (1:30).** Click a dot on the selected route. Show mile, ETA, wind, rain, snow, each factor's level, and the final level. If the forecast is calm, say how a load rule would change it: wind 45–54 mph with more than 30,000 lb becomes No Travel. Mention unknown weather is shown as unknown and is not treated as Low.

4. **Heatmap (1:30).** Drag the 0–48 hour slider and hit play. Say the corridor forecast is already in memory: the slider does not call the server. On a long trip, the motion should stay smooth.

5. **Code (1:30).** Open `backend/planner/domain/risk.py`, `ranking.py`, and `backend/planner/tests/test_risk.py`. Then `planner/services/plan_trip.py`: one weather fetch per rounded coordinate, cached, shared by every route and the heatmap.

6. **Assumptions (0:30).** Interval is chosen by the user, default 25 miles. Wind is the sustained 10 m speed. ETA is distance-proportional using the routing API's car duration. Ranking follows the brief. No accounts, no saved trips. Next: a truck speed profile and per-leg durations.

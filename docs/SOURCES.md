# SOURCES

For each data source: what real-world format was researched, what was learned,
what the sample data looks like and why, and what would break in a real deployment.

---

## 1. SAP — Fuel & Procurement (Scope 1)

### Format researched

SAP Materials Management (MM) module, movement type reporting via transaction MB51
(material document list). The extract is a flat file produced by the ABAP list display,
typically tab- or semicolon-delimited, with column names in either English or German
depending on the system locale.

The canonical table is **MSEG** (material document segment), joined with MKPF (header)
for the posting date. Key fields:

| SAP field | Meaning | Example |
|-----------|---------|---------|
| MBLNR | Material document number | 4900005000 |
| MJAHR | Material document year | 2024 |
| ZEILE | Line item number | 0001 |
| BUDAT | Posting date | 20240115 (YYYYMMDD) |
| WERKS | Plant code | IN01 |
| MATNR | Material number | MAT-1000 |
| MAKTX | Material description | Diesel (HSD) |
| MENGE | Quantity | 2500.00 |
| MEINS | Unit of measure (SAP) | L |
| BWART | Movement type | 201 |
| KOSTL | Cost centre | CC001 |

**German column variant** (system locale DE): `Buchungsdatum` instead of `BUDAT`,
`Menge` instead of `MENGE`, `Basismengeneinheit` instead of `MEINS`, etc.
Our parser handles both via `COLUMN_ALIASES`.

**Date format:** Always `YYYYMMDD` in BUDAT, but some clients export via Excel and
the date becomes `DD.MM.YYYY` or `DD/MM/YYYY`. Our `parse_sap_date()` tries all
common formats in order.

**Unit of measure codes:** SAP uses its own UoM vocabulary: `L` (litre), `GAL`
(US gallon), `M3G` (gas cubic metre), `MMBTU`, etc. We maintain a conversion map
(`SAP_UOM_MAP`) covering the most common ones.

### What was learned

- Movement type 201 = goods issue to cost centre (direct consumption). This is the
  right filter for fuel consumption.
- Movement type 261 = goods issue to production order (also consumption, but tied
  to a manufacturing order — relevant if the client tracks production-based fuel use).
- Movement type 501 = receipt without PO (not consumption, ignore).
- Plant codes (WERKS) are 4-character alphanumeric and mean nothing without a
  lookup table — `IN01` might be the Pune factory, or the client's first India site,
  or a legacy code from an acquisition. We store them as-is and let the analyst
  maintain the facility name mapping.
- Some SAP systems export MENGE with a comma as decimal separator (German locale):
  `2.500,00` means 2500, not 2.5. Our parser handles this with `.replace(",", ".")`.

### Sample data (`sap_mseg_export_sample.csv`)

Tab-delimited. 13 rows, covering Q1 and part of Q2 2024. Mix of plants (IN01, IN02,
IN03), fuel types (diesel, petrol, LPG, natural gas), and one non-mappable material
(Furnace Oil) which intentionally has no emission factor, producing a record with
`kg_co2e = null` and status "pending" — forcing analyst review.

The document numbers are in the `490XXXXXXX` range, which is the typical SAP
numbering for MM movements (number range 49 is standard for goods issues).
The cost centre codes (CC001–CC010) are plausible for a manufacturing company
with three plants.

### What would break in a real deployment

1. **Material master mapping:** Without a MATNR → fuel type mapping, we rely on
   description text matching. If the client uses material numbers as descriptions
   (e.g. "MAKT: 40012345" instead of "Diesel"), the fuel pattern regex fails.
   Solution: ask the client for a MARA/MAKT extract (material master) to build
   an explicit mapping.

2. **Multiple SAP clients / company codes:** Large enterprises run multiple SAP
   logical systems. An export from client 100 may have different plant codes than
   client 200. We'd need to know which logical system each batch came from and
   maintain separate lookup tables.

3. **Batch vs. process orders:** Movement type 261 against a process order (PP-PI)
   means the fuel is consumed by a production process, not directly by a cost centre.
   Attribution to a facility is then indirect. The current model doesn't handle this.

4. **Negative quantities (reversals):** Movement type 202 reverses 201. A reversal
   appears as a negative MENGE. Our parser currently skips non-positive quantities
   with an error. Production would need to handle reversals by crediting the
   original record.

---

## 2. Utility Portal CSV — Electricity (Scope 2)

### Format researched

**BESCOM (Bangalore Electricity Supply Company):** Consumer portal at bescom.in.
The billing history export is a CSV with columns: Account Number, Bill Period,
Units Consumed (kWh), Bill Amount, Due Date. Billing period is approximately 60 days
(bi-monthly reading cycle), not calendar months.

**PG&E (Pacific Gas & Electric, California):** Green Button CSV export. Columns:
Start Date, End Date, Usage (kWh), Cost (USD), Unit (kWh). Available for up to
12 months of history. 15-minute interval data is available but we aggregate to
billing period for simplicity.

**British Gas (UK):** Business energy portal. Columns: Service Period Start,
Service Period End, Electricity kWh, Gas Volume (m³), Tariff, Amount Due.
Note: electricity and gas are on the same row in their export — we extract only kWh.

**Con Edison (New York):** Columns: Invoice Date, Service Period Start, Service Period End,
Electricity (kWh), Demand (kW), Amount Due. The "Demand" column (in kW, not kWh)
is peak demand for capacity pricing — we ignore it for emission purposes.

### What was learned

- Billing periods are almost never calendar months. BESCOM reads bi-monthly
  (15th of even months, roughly). PG&E reads monthly but on a cycle date (e.g.
  17th to 16th). This means aggregating to reporting quarter requires apportioning
  across periods — the current implementation stores `activity_period_start` and
  `activity_period_end` so that apportioning can be done correctly at report time,
  even though we don't implement it in this prototype.

- Multi-meter accounts: a client with multiple sites will have one row per meter
  per billing period. We deduplicate on `(meter_id, period_start, kwh)` hash.

- The Indian grid emission factor (CEA 2022-23 national average: 0.7082 kgCO2e/kWh)
  is substantially higher than the UK (0.212) or US average (0.386). Applying the
  wrong factor would produce a 3× error in Scope 2. Our parser requires explicit
  country code selection at upload time.

### Sample data (`utility_bescom_sample.csv`)

11 rows, three meters:
- `MTR-BLR-001`: Bangalore HQ, ~14,000 kWh/period (office scale)
- `MTR-BLR-002`: Bangalore factory floor, ~82,000–91,000 kWh/period (industrial scale)
- `MTR-PNQ-001`: Pune office, ~10,000 kWh/period

Billing periods start on the 15th (BESCOM convention) and run 30 days.
The factory floor shows ~8% seasonal variation (higher in April–May due to cooling
load). The tariff rates (₹7.5/kWh) are realistic for BESCOM's commercial tariff
(HT-2 tariff) as of 2024.

### What would break in a real deployment

1. **Column name variation:** We handle ~20 common column name variants, but a
   utility we haven't seen before will have a different name. The parser will return
   "no kWh column found" error. Solution: let the analyst map columns manually, or
   add a column-mapping step to the UI.

2. **Multi-fuel bills:** British Gas exports electricity and gas kWh on the same row.
   The current parser only extracts electricity. Natural gas consumption (Scope 1)
   needs a separate extraction path.

3. **Time-of-use (TOU) tariffs:** Some utilities export separate rows for peak/off-peak.
   The current parser sums all kWh rows for the same meter/period. This is correct
   for emission purposes (all kWh has the same grid factor regardless of when it was
   consumed — unless the client has a renewable tariff, which is the market-based
   accounting problem described in TRADEOFFS.md).

4. **Interval data:** PG&E's Green Button export can provide 15-minute interval data.
   For a client that wants to claim renewable certificates against specific hours,
   this matters. We aggregate to billing period and discard interval data.

---

## 3. Corporate Travel — Flights, Hotels, Ground (Scope 3, Category 6)

### Format researched

**Concur expense report export:** CSV with columns including Report Name, Report ID,
Employee Name, Employee ID, Transaction Date, Expense Type (Airfare/Hotel/Car Rental),
Amount, Currency, Merchant Name, From City, To City, Departure Airport, Arrival Airport,
Miles, Flight Class. Available from Concur's reporting module → Export → CSV.

**Navan (formerly TripActions) trip export:** CSV with columns trip_id, traveler_email,
travel_type (flight/hotel/car/rail), departure_date, arrival_date, origin_iata,
destination_iata, cabin_class, distance_km, hotel_name, hotel_city, hotel_nights,
car_type. Available from Navan admin → Reports → Trip Report → Export.

**GHG Protocol Scope 3 Category 6 guidance:** Distance-based method (preferred when
distance data available). Emission factors from DEFRA 2023 GHG Conversion Factors for
Company Reporting, Table 11 (air travel) and Table 14 (hotels).

**DEFRA 2023 factors used:**
- Domestic flight (<500 km): 0.2553 kgCO2e/pkm (includes RFI uplift)
- Short-haul (500–3,700 km): 0.1557 kgCO2e/pkm
- Long-haul (>3,700 km): 0.1950 kgCO2e/pkm
- Business class multiplier: ×2.0 (DEFRA methodology)
- First class multiplier: ×2.4
- Hotel: 31.0 kgCO2e/night (IEA world average)
- Taxi/car: 0.1489 kgCO2e/km (average car, DEFRA 2023)

### What was learned

- Concur does not always include distance. When only airport codes are present,
  distance must be calculated. We use haversine from a coordinate table of 50
  airports. The OAG Schedules dataset or the OpenFlights database (open-licensed)
  would cover all ~9,000 IATA codes.

- The "Expense Type" field in Concur is user-entered and inconsistent. One employee
  enters "Airfare", another "Air Travel", another "Flight". Our parser normalises
  against a set of patterns but will miss unusual entries (e.g. "International Trip").

- Hotel emission factors vary enormously by country and star rating. 31 kgCO2e/night
  is a global average from IEA. Cornell Hospitality Research found that a 5-star hotel
  in a high-emitting grid averages ~80 kgCO2e/night. For a prototype this is acceptable;
  production should use country-specific factors (DEFRA has UK-specific hotel factors).

- Return flights: Concur sometimes exports one row per direction (outbound + return),
  sometimes one row for the round trip. We treat every row as a one-way trip. If the
  client exports round trips as a single row, we'd double-count. This should be clarified
  in the data spec with the client.

### Sample data (`navan_travel_export_sample.csv`)

45 rows: 25 flights (mix of domestic India and international), 12 hotel stays, 8 ground
transport entries. Travellers are the expected executive team (CEO, CFO, VP Sales, etc.).

International flights (BLR→LHR, DEL→JFK, etc.) use business class for the CEO/CFO,
economy for others — matching realistic corporate travel policies. Hotel stays
correspond to the destination cities of the international flights. Ground transport
entries include both taxi (short, no distance — defaults to 20 km estimate) and car
rental (with explicit distance).

Several rows intentionally have blank `origin_iata`/`destination_iata` with no
`distance_km` — these will fail parsing and appear in the error log for analyst review,
demonstrating the error surfacing mechanism.

### What would break in a real deployment

1. **Unknown airports:** Our haversine table covers 50 airports. Any flight to a
   secondary airport (e.g. BBI - Bhubaneswar, CCJ - Calicut) will fail if no distance
   is provided. Solution: integrate OAG or the OpenFlights database.

2. **Rail travel:** Currently goes to `ground_transport` with a generic taxi emission
   factor. Rail has a much lower factor (0.041 kgCO2e/km for average EU rail, DEFRA).
   Navan exports include `travel_type: rail` but we map it to ground. Should be a
   separate category.

3. **Currency conversion:** Concur exports amounts in the transaction currency. We
   store them in `extra` but don't convert to a base currency. For reporting,
   spend-based emission methods (when distance isn't available) need a base currency.

4. **Employee vs. guest vs. non-employee travel:** Concur can include travel booked
   for clients or candidates. These shouldn't be in Scope 3 Category 6. The current
   parser has no way to distinguish. A `department_code` or `travel_policy` column
   would help.

5. **Aggregation at the individual record level:** GHG Protocol allows reporting
   business travel as an aggregate (total pkm per flight class per year) rather than
   individual trips. Individual record tracking is more auditable but raises privacy
   questions — traveller email addresses are stored in `extra`. In production, the
   privacy policy would need to address this.

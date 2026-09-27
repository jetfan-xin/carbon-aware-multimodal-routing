# Operator and market-data calibration

No public end-to-end Chongqing--Shanghai order table was found. The model instead keeps operator corridor disclosures, official market indices, historical same-corridor operations, a public drayage observation, team-collected distances and remaining assumptions distinct at field level.

Key replacements include:

| Field | Maintained value | Limitation |
| --- | --- | --- |
| Road / rail / water comparison | CNY 15,000 / 4,600 / 1,400 per 20-ft | Public corridor comparison; inclusions incomplete |
| Historical rail time | 55 / 57.5 / 60 h | Historical Yangpu--Tuanjiecun evidence, not a current timetable |
| Express water time | 8--9 days | Published service range; booking wait unknown |
| Regular water | 240 h and CNY 1,130 FIO | Current time and official index; not one door-to-door quote |
| Luchaogang--Yangshan | about 45 km and one CNY 200 posting | Not a contract average or completed order |
| Mode emissions | 0.076 / 0.003 / 0.020 kgCO2e/(t-km) | Default factors, not equipment measurements |

All source URLs and field evidence classes are recorded in [`sources.json`](../data/facility_network/sources.json) and [`model_inputs.json`](../data/facility_network/model_inputs.json). Different years, endpoints and price scopes are not silently merged into a claimed invoice.

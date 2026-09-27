# Yangtze corridor and Yangtze River Delta facility network

## Purpose

The historical workbook uses city names and mode-specific city-pair distances. A city in that table does not prove that a suitable port, rail terminal, service, tariff or transfer operation exists. The maintained evidence layer therefore separates:

1. planning or hub status, which may justify a candidate location;
2. a resolved facility and its documented mode/transfer capability;
3. an operational service with endpoints, date, distance, time and tariff;
4. a calibrated model edge, whose missing fields are filled only by explicitly labelled assumptions.

The registry contains 20 candidate facilities, 15 exactly resolved facilities, 12 service-evidence records and five transfer records. None of the raw public service records currently satisfies every optimizer field, so `optimizer_eligible_services` remains zero. The separate calibrated layer contains seven numeric edges, one facility-specific transfer and three runnable cases.

The network uses two geographic scopes: external Yangtze corridor gateways and facilities inside the Yangtze River Delta. Historical and current snapshots remain separate; a service announced after 2022 is not backdated into the competition case.

The only admitted multileg Chongqing--Yangshan alternative is Guoyuan --rail--> Luchaogang --road--> Yangshan. Wuhu and Nanjing are retained as independently documented corridor references, not invented calls or free transfer points on the Chongqing service.

Machine-readable evidence is under [`data/facility_network`](../data/facility_network/), and the generated inventory and schematic are under [`benchmarks/facility-network`](../benchmarks/facility-network/).

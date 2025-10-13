Index	Column	Data Type	Purpose	Needed in alerts.html
0	id	INTEGER	PK, not shown in table	Yes
1	symbol	TEXT	Stock symbol	Yes
2	name	TEXT	Full stock/company name	Yes
3	price	REAL	Last E*TRADE price	Yes
4	vwap	REAL	VWAP	Yes
5	vwap_diff	REAL	VWAP diff (local calc)	Yes
6	qty	INTEGER	Simulated qty to buy	Yes
7	buy	INTEGER	Sim buy flag	Yes
8	timestamp	TEXT	Time of alert (string)	Yes
9	triggers	TEXT	Comma/emoji triggers	Yes
10	sparkline	TEXT	SVG/URL	Yes
11	cleared	INTEGER	For "clear" feature	Not in table, logic only

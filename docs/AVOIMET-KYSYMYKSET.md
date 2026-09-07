# Avoimet kysymykset

*Ei "future work" -lista vaan tutkimuskysymyksiä, joihin seuraavat versiot
vastaavat. Kirjattu tähän, koska hyvä kysymys vanhenee hitaammin kuin hyvä
vastaus.*

---

## K1. Mikä hiljainen tieto on koodattavissa?

Tausta: olen ollut yhdeksän vuotta johtoryhmän kyljessä ihmisen muotoisena
semanttisena kerroksena. Käännän *"mitä johtoryhmä tarkoittaa"* muotoon *"mikä
kysely antaa sen"*. Kerros on siis jo olemassa — se on päässäni.

Tämä repo on kokeilu siitä, mikä osa siitä on siirrettävissä ulos. Alustava
luokittelu koodattavuuden mukaan:

| Tyyppi | Esimerkki | Koodattavissa? |
|---|---|---|
| **Määritelmät** | mikä lasketaan mukaan, mikä ei | Kyllä — suoraan katalogiin |
| **Kirjauskynnykset** | `reps ≤ 12`; alle X € ei jaksoteta | Kyllä — ja **kuuluu** kirjata, koska nämä ovat päätöksiä, joita ei ole missään |
| **Haistelusäännöt** | *"jos tämä luku on yli X, jokin on rikki"* | **Kyllä — ja tämä on aliarvostetuin.** Kokeneen ihmisen "haistan että tuo on väärin" on yleensä 5–10 kirjoittamatonta sääntöä. Ne kääntyvät testeiksi. |
| **Kysymyskartta** | millä sanoilla johtoryhmä oikeasti kysyy mitäkin | Kyllä — tämä *on* routerin esimerkkikysymyslista |
| **Vakiotulkinnat** | *"jos myynti laskee mutta kate nousee, se on yleensä X"* | Osittain — hypoteesilistaksi, **ei** johtopäätökseksi |
| **Konteksti** | *"tämä kuu on vääristynyt yritysoston takia"* | Ei — mutta **lippu** on: "tässä kaudessa on merkitty poikkeus, kysy ihmiseltä" |
| **Politiikka** | kuka ei halua nähdä mitä | Ei, eikä kuulukaan |

Raja, jota tämä hakee:

> **Määritelmä on siirrettävissä. Harkinta ei ole.**

Molemmat ovat samassa päässä: *"kate lasketaan näin"* (määritelmä) ja *"mutta
tämän kuun luku on vääristynyt yritysoston takia, älä lue sitä suoraan"*
(harkinta). Ensimmäinen kuuluu ulos — silloin se on tarkastettavissa,
testattavissa, johdonmukainen, eikä se lähde talosta silloin kun ihminen
lähtee. Jälkimmäinen ei kuulu ulos, ja jokainen yritys automatisoida se tuottaa
itsevarmoja vääriä vastauksia.

**Seuraava askel:** haistelusäännöt. Kirjaa ylös 10–15 sääntöä, joilla
tunnistan väärän luvun ilman että lasken mitään, ja katso kuinka moni niistä
kääntyy suoraan testiksi. Se on myös agenttitiimin turvallisin ensimmäinen
käyttötapaus: agentti, joka ei tuota lukuja vaan kyseenalaistaa niitä.

**Huomio, joka pitää tehdä ensin:** rajaa mukaan vain se, mikä ei ole
liiketoimintaherkkää. Määritelmien rakenne on yleistä osaamista; tietyn
yrityksen kynnysarvot eivät ole.

---

## K2. Missä oma näkemykseni on vanhentunut?

Kaksi havaintoa, joita en itse ollut sanoittanut, ja jotka kannattaa merkitä
tarkistettaviksi:

**a) Olin puolisokea sille, että semanttinen malli on jo olemassa.** Tilikartta
ja kustannuspaikkahierarkia *ovat* mittarimäärittely. Ne eivät vain ole
koneluettavia, ja ne asuvat dokumentissa, jota kukaan ei ole avannut kolmeen
vuoteen. Kysymys ei siis ole "rakennetaanko semanttinen kerros" vaan
"tehdäänkö olemassa olevasta koneluettava".

**b) Riski ei ole se, että työkalut ovat vaihtuneet.** Se on oletus siitä, että
**pullonkaula on edelleen luvun saaminen**. Jos luvun saaminen halpenee, niukka
taito siirtyy kahteen muuhun: *minkä kysymyksen esittää* ja *milloin luku
valehtelee*.

Tämä on tarkoituksella kirjattu kysymyksenä eikä vastauksena — se on testattava
väite, ei totuus. Ja jos se pitää paikkansa, oma kehityskohde on kysymysten
esittäminen, ei laskeminen.

Käytännön havainto tästä repoista: **täsmäytyssarjan kirjoittaminen on tuon
taidon harjoittelua.** Kahdenkymmenen kysymyksen kirjoittaminen — erityisesti
niiden monitulkintaisten ja niiden, joihin pitää kieltäytyä vastaamasta — on
sama työ kuin sen miettiminen, mitä johtoryhmä oikeasti kysyy ja mihin ei ole
vastausta.

---

## K3. Milloin "agentti" on oikeasti pelkkä tietovarastotesti?

Käsitelty kokonaisuudessaan tiedostossa [AGENTIN-MUOTO.md](AGENTIN-MUOTO.md).
Lyhyt versio: useimmiten. Ja se on hyvä uutinen, ei huono.

---

## K4. Kuinka pitkälle sama moottori kantaa toiseen domainiin?

Katalogin lataus on monikatalogiseksi rakennettu (`semantic/catalogs/*.yml`),
mutta vain yksi katalogi on toteutettu. Avoin kysymys: kuinka paljon koodia
joutuu muuttamaan, kun rinnalle tulee **budjetti vs. toteuma kustannuspaikoittain**
-katalogi samalle moottorille?

Ennuste, joka kannattaa kirjata ennen kokeilua, jotta sen voi todeta vääräksi:
kääntäjään ei tarvitse koskea, mutta `grain`-arvot (`challenge` / `lifter`) ovat
kovakoodattuja `catalog.py`:ssä ja joutuvat yleistymään.

---

## K5. Mistä katalogin määritelmät oikeasti tulevat?

Tässä repossa ne kirjoitti rakentaja. Oikeassa organisaatiossa ne pitäisi
kirjoittaa niiden, jotka omistavat luvun — ja he eivät kirjoita YAML:ia.

Avoin kysymys: onko ero YAML-tiedoston ja määrittelykeskustelun välillä
työkalukysymys (lomake, käyttöliittymä) vai ei kumpikaan — eli onko oikea
tuotos katalogi vai se, että joku joutui päättämään.

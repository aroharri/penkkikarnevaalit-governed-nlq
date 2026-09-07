# Missä tämä ei toimi

Tämä luku on repossa siksi, että ilman sitä muu olisi myyntipuhetta. Jos
lähestymistavan rajoja ei ole kirjattu, lukija ei voi tietää, tunteeko
rakentaja ne.

## 1. Portit eivät takaa, että vastaus on se jota tarkoitit

Tämä on tärkein kohta, ja se on helppo lukea väärin.

Portit takaavat, että ulos tuleva luku on **määritelty mittari, oikein
laskettuna ja täydellisellä lähdeviitteellä**. Ne takaavat myös, että selvästi
monitulkintainen kysymys johtaa tarkennukseen eikä arvaukseen.

Ne **eivät** takaa, että valittu mittari on se, jota kysyjä tarkoitti.

Portit eivät näe aikomusta. Jos router palauttaa yhden ehdokkaan suurella
varmuudella, tasapeliportti ei laukea — vaikka ehdokas olisi väärä. Täsmäytys
mittaa juuri tätä: kehityksen aikana sääntörouter vastasi itsevarmasti
kysymykseen *"Mikä on tavoite?"*, vaikka kaksi kilpailevaa tavoitelukua on koko
katalogin pointti. Se näkyi täsmäytyksessä `VÄÄRÄ LUKU` -sarakkeessa, ja
vihjetaulukko korjattiin.

Se, mikä suojaa lukijaa tässä kohdassa, ei ole portti vaan **lähdeviite**:
vastaus kertoo mikä mittari valittiin, millä kaavalla ja millä rajauksella,
joten väärä valinta on *näkyvä* virhe eikä hiljainen.

Ero perinteiseen text-to-SQL:ään ei siis ole "tämä ei voi olla väärässä" vaan
**"kun tämä on väärässä, sen näkee"**.

## 2. Kaikki laskenta ei ole muotoa `agg(x)` tai `agg(x) / agg(y)`

Katalogi on tarkoituksella tyhmä: mittari on aggregaatti sarakkeesta tai
kahden sellaisen suhde tai erotus. Se kattaa juuri ne luvut, joista
johtoryhmässä kiistellään — suhdeluvut ja poikkeamat.

Se ei kata:

- kauden yli kulkevia vertailuja (edellinen vuosi, liukuva 12 kk)
- juoksevia saldoja ja semi-additiivisia mittareita (varastosaldo, henkilöstömäärä)
- jakoperusteita ja allokointeja
- valuuttamuunnosta eri kursseilla eri kausina
- siltalaskelmia ja poikkeaman komponenttiajoa

Jokainen semanttisen kerroksen tuote törmää tähän seinään ja lisää sitten
poikkeusluukun, johon saa kirjoittaa vapaata SQL:ää. Siinä hetkessä YAML:sta
on tullut ohjelmointikieli — mikä on huonompi kuin ohjelmointikieli, koska
siinä ei ole työkaluja, testejä eikä tyyppejä.

**Tässä repossa poikkeusluukkua ei ole, ja se on valinta eikä puute.** Mittari,
jota ei voi ilmaista näin, ei mene katalogiin. Se on ad hoc -analyysiä ja se
merkitään sellaiseksi.

## 3. Määrittely ei ole vaikea osa — sopiminen on

Kun johtoryhmässä kiistellään liikevaihdosta, ongelma ei ole tekninen. Myynti,
talous ja toimitusjohtaja tarkoittavat kolmea eri asiaa.

YAML ei luo sopua. Se tekee erimielisyyden **näkyväksi** ja pakottaa jonkun
päättämään. Se on arvokasta, mutta se on organisatorinen kustannus, ei
tekninen voitto — ja se on yleisin syy, miksi nämä hankkeet kuolevat: kukaan ei
halua olla se, joka allekirjoittaa määritelmän.

Tässä repossa se maksettiin kahdesti, pienessä mittakaavassa: kumpi 1RM on *se*
1RM (sovelluksen tallentama vai lähdedatasta laskettu), ja kumpi tavoite on *se*
tavoite (haasteen oma vai jäsenten summa). Kummassakin oli kaksi puolustettavaa
vastausta. Ne on kirjattu, koska kirjaamatta jättäminen olisi tarkoittanut, että
valinta tehdään joka kerta uudestaan eikä kukaan tiedä mikä se oli.

## 4. Mittarit lisääntyvät, eikä kukaan omista niitä

Kahdeksan mittaria on elegantti. Kolmesataa mittaria YAML:ssa on toinen
koodipohja, jota kukaan ei ylläpidä, ja se ajautuu erilleen oikeasta
raportoinnista.

Realistinen malli on **pieni joukko hallittuja otsikkomittareita** — ne 10–30,
joista oikeasti kiistellään — ja vapaa analyysi katalogin ulkopuolella
selvästi merkittynä.

Ja ilman nimettyä omistajaa katalogi mätänee nopeammin kuin Excel. Excel-
tiedostossa on ainakin aina joku ihminen kiinni. Omistamattomassa YAML:ssa ei
ole.

## 5. Sääntörouter on huono, eikä sitä pidä esittää muuna

Avaimeton router on avainsanahaku. Se ei ymmärrä kysymystä, se tunnistaa
sanoja. Täsmäytystaulukko tulostaa sen pistemäärän LLM-routerin vieressä
nimenomaan siksi, ettei eroa tarvitse arvailla.

Sen tehtävä on kaksi asiaa: klooni toimii ilman tunnuksia, ja **portit ovat
testattavissa kahdella eri routerilla**. Jos sääntörouter tuottaisi väärän
luvun jota LLM-router ei tuota, turva tulisi mallista eikä porteista — ja
silloin koko väite olisi eri.

## 6. Mitä tämä ei ole

Tämä ei ole agenttitiimi eikä text-to-SQL. Se on **yksi** reitti kysymyksestä
lukuun, ja reitti on tarkoituksella kapea.

Laajemmasta rakennelmasta ja siitä, mikä tässä silmukassa yleistyy ja mikä ei,
katso [AGENTIN-MUOTO.md](AGENTIN-MUOTO.md) ja
[AVOIMET-KYSYMYKSET.md](AVOIMET-KYSYMYKSET.md).

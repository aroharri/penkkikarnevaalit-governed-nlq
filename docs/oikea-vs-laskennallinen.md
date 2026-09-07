# Miksi "toteuma" ei ole yksi luku

*Tämä dokumentti on kirjoitettu niin, ettei siihen tarvitse kumpaakaan taustaa —
ei voimanoston eikä taloushallinnon.*

## Lähtötilanne

Neljän hengen porukalla on yhteinen tavoite: **600 kg yhteenlaskettua
ykkösmaksimia**. Ykkösmaksimi tarkoittaa suurinta painoa, jonka nostaja saa
ylös yhden kerran.

Mittari näyttää tällä hetkellä **538,3 kg**. Se on 89,7 % tavoitteesta, ja
61,7 kg puuttuu.

Mutta se 538,3 ei ole yhtä lajia.

## Kaksi eri lukua samassa summassa

Sovelluksessa nostaja kirjaa **painon ja toistojen määrän** — ei
ykkösmaksimiaan. Ykkösmaksimi lasketaan siitä Brzyckin kaavalla:

```
ykkösmaksimi = paino × 36 / (37 − toistot)
```

Ja tästä seuraa jako, jota summa ei näytä:

| Kirjaus | Kaavan kerroin | Tulos | Mikä se on |
|---|---|---|---|
| 100 kg × **1** toisto | 36/36 = **1,000** | 100,0 kg | **Oikea ykkösmaksimi.** Hän nosti 100 kg. |
| 80 kg × 5 toistoa | 36/32 = 1,125 | 90,0 kg | **Laskennallinen ykkösmaksimi.** Kukaan ei ole nostanut 90 kg. |

Huomaa yhden toiston rivi. Kerroin ei ole *melkein* yksi — se on **tasan yksi**,
koska `37 − 1 = 36`. Kaava ei siis arvioi tarkasti yhdellä toistolla; se
lakkaa arvioimasta. Luku on havainto.

Kaikki muut rivit ovat mallin tuotoksia. Ne ovat päteviä lukuja — Brzycki on
laajasti käytetty ja kohtuullisen tarkka 1–12 toistolla — mutta ne ovat
**arvioita tapahtumasta, joka ei tapahtunut**.

## Ja tältä se näyttää oikeassa datassa

```
Porukan yhteistulos              538,3 kg   /  600 kg      89,7 %

  josta oikeaa ykkösmaksimia     140,0 kg      26 %
       laskennallista            398,3 kg      74 %
```

Kolme neljäsosaa "toteumasta" on mallin tuotos. Se ei tee luvusta väärää.
Se tekee siitä **eri varmuusasteista koostuvan** — ja summa piilottaa sen.

## Sama rakenne talousraportoinnissa

Kuukauden **toteuma** ei ole yksi luku sekään. Se sisältää sekä toteutuneita
tapahtumia että jaksotuksia ja arvioita, jotka syntyvät laskentasäännöstä.
Kukaan ei yleensä sano sitä ääneen, ja siksi kukaan ei muista sitä silloin kun
pitäisi.

Vertaa näitä kahta riviä:

> Toteuma 528 t€ budjetista 600 t€.

> Toteuma 528 t€ budjetista 600 t€ — josta 312 t€ toteutunutta ja
> 216 t€ arvioperusteista.

Johtoryhmä tekee päätöksen ensimmäisen rivin perusteella. Toinen rivi ei ole
vaikeampi tuottaa. Sitä ei vain yleensä pyydetä, koska jako on kadonnut jo
siinä vaiheessa kun luvut summattiin yhteen.

Rinnastus on suora:

| Nostodata | Talousraportointi |
|---|---|
| 1 toisto → havainto | kassaan tullut euro |
| 2–12 toistoa → Brzycki-arvio | jaksotettu tai arvioperusteinen erä |
| yli 12 toistoa → ei kirjata | kirjauskynnyksen alle jäävä erä |

## Mitä tämä katalogi tekee asialle

Kaksi asiaa, ja kumpikaan ei ole nokkela:

**1. Varastossa on `one_rm_source`-kenttä**, joka merkitsee jokaisen kirjauksen
joko oikeaksi (`true_max`) tai laskennalliseksi (`brzycki_estimate`). Merkintä
tehdään rivikohtaisesti siinä hetkessä, kun luku syntyy — ei jälkikäteen
arvaamalla.

**2. Jako tulostuu aina**, kun mittari on kilosumma. Sitä ei tarvitse pyytää
eikä sitä voi unohtaa pyytää.

Sääntö, jota tämä ilmentää:

> **Kun luku syntyy kahdesta eri varmuusasteesta, jako kuuluu näkyviin — ei
> alaviitteeseen.**

## Yksi asia, joka piti päättää

Sovellus tallentaa **oman** `estimated_1rm`-kenttänsä jokaiselle kirjaukselle.
Tämä repo laskee luvun **uudelleen lähdedatasta** eikä lue sitä kenttää.

Kilpailevia lukuja oli siis kaksi, ja jompikumpi oli valittava. Peruste
valinnalle: yksi laskentapaikka, joka on luettavissa ja tarkastettavissa.
Sovelluksen kenttä on edelleen olemassa täsmäytystä varten — sisarrepo
`penkkikarnevaalit-analytics` ajaa testin, joka vaatii lukujen olevan 0,5 kg:n
sisällä toisistaan.

Sama tilanne toistuu tavoiteluvun kohdalla: haasteen oma tavoite (600 kg) ja
jäsenten henkilökohtaisten tavoitteiden summa ovat kaksi eri lukua. Katalogi
pitää molemmat omina nimettyinä mittareinaan (`crew_goal_kg` ja
`crew_member_target_sum_kg`) sen sijaan että piilottaisi toisen toisen taakse.

Se on tämän lähestymistavan varsinainen työ. Ei laskeminen — **sen
päättäminen, mikä luku on se luku, ja sen kirjaaminen ylös.**

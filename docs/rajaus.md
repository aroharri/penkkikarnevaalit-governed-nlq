# Rajaus: miksi jokaisella mittarilla on pakollinen raja

Jokainen tämän katalogin mittari julistaa `scope: challenge`. Ilman rajausarvoa
kääntäjä **nostaa poikkeuksen** — se ei tuota laajempaa kyselyä.

Se kuulostaa ankaralta yhden haasteen datalle. Syy näkyy siinä, mitä tapahtuu
kun rajaus puuttuu, ja virhe menee **kahteen suuntaan**.

## Suunta 1: ylirajaus — luku on liian suuri ja väärälle yleisölle

Kysely, jota ei ole rajattu, vetää mukaan kaikki rivit. Käytännössä:

> Analytics engineer hakee "meidän yksikön" luvut. Rajaus jää pois. Raportti
> menee johtoryhmään, ja siinä on mukana **naapuriyksikön** luvut.

Tämä ei ole pyöristysvirhe. Se on kaksi ongelmaa kerralla:

1. **Luku on väärä** — se sisältää rivejä, jotka eivät kuulu kysymykseen.
2. **Luku on väärälle yleisölle** — se näyttää yhden ryhmän tiedot toiselle.

Jälkimmäinen ei korjaannu sillä, että luku myöhemmin korjataan. Se on jo nähty.

Tässä repossa sama tilanne: sovelluksessa voi olla useita haasteita, ja
tavoiteluku on haastekohtainen. Rajaamaton `crew_total_1rm_kg` laskisi yhteen
eri haasteiden nostajat ja vertaisi summaa yhden haasteen tavoitteeseen.

## Suunta 2: alirajaus — luku on liian pieni eikä kukaan huomaa

Datassa on **viides käyttäjä, joka ei kuulu mihinkään haasteeseen**. Hän on
olemassa, hän on tunnus järjestelmässä, ja hän ei osu yhteenkään mittariin.

Se on oikea lopputulos. Mutta se on myös se tapa, jolla luku kutistuu hiljaa:

> Kirjaus ilman kustannuspaikkaa. Kustannuspaikka, jota ei ole hierarkiassa.
> Rivi katoaa summasta, eikä täsmäytys huomaa — koska kukaan ei laske
> molempia puolia.

Siksi orpo **ei ole rajattu pois tuonnista**. Hän on datassa, hänet rajataan
pois mittarin määrittelyssä, ja vastauksen lähdeviite sanoo sen ääneen:

```
Jasenia       4  (datassa 5 kayttajaa; 1 ei kuulu tahan haasteeseen, ei mukana)
```

Sama koskee nollarivejä. Jos jäsen ei ole treenannut aikaikkunan sisällä, hän
näkyy nollana eikä katoa listalta. Ero on luettavuudessa:

- **Nimi puuttuu listalta** → lukija ymmärtää: "häntä ei kysytty."
- **Nimi näkyy nollana** → lukija ymmärtää: "kysyttiin, ja vastaus on ei yhtään."

Vain toinen niistä on totta. Ilman riviä lukija ei voi tietää kumpi.

## Miksi valvonta on kääntäjässä eikä säännössä

Rajauksen voisi tarkistaa portissa: "jos rajaus puuttuu, kysy." Se toimii,
kunnes joku lisää uuden kutsupolun ja unohtaa.

Siksi lukko on alempana. `semantic/catalog.py` toimii näin:

- Mittari ilman `scope`-kenttää → **katalogi ei lataudu lainkaan**
- `compile()` ilman rajausarvoa → **poikkeus**
- Käännetty SQL ilman rajauspredikaattia → **poikkeus** (viimeinen varmistus)

Kolmatta vaihtoehtoa ei ole. Testi `test_no_metric_can_compile_without_a_scope_value`
käy läpi katalogin **jokaisen** mittarin ja varmistaa, että se joko tuottaa
rajatun SQL:n tai kaatuu.

Ero on olennainen: sääntö on lupaus, että joku muistaa. Kääntäjän poikkeus on
se, ettei muistaminen ole tarpeen.

## Kun rajaus ratkeaa itsestään

Nykyisessä datassa haasteita on yksi. Silloin kysymys "paljonko porukalta
puuttuu?" ei ole monitulkintainen, ja järjestelmä ratkaisee rajauksen — mutta
**lukee sen ääneen vastauksen ensimmäisellä rivillä**:

```
Rajaus: Penkkikarnevaalit 2026  (ainoa datassa -- ratkaistu automaattisesti)
```

Kun toinen haaste ilmestyy, sama koodi alkaa kysyä. Ei erikoistapausta, ei
myöhempää korjausta — testi `test_two_challenges_cannot_be_inferred_so_the_gate_asks`
todistaa sen jo nyt toisella aineistolla.

## Ja kun kysymys ylittää rajan tarkoituksella

Kysymys *"kuka on vahvin kaikista käyttäjistä?"* ei ole laajempi versio
kysymyksestä *"kuka on vahvin tässä haasteessa?"*. Se on **eri kysymys**, ja
siihen vastaaminen näyttäisi toisten haasteiden nostajia.

Se kieltäydytään, ei laajenneta.

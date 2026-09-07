# Agentin muoto

*Arkkitehtuurihavainto jatkokehitystä varten. Tässä repossa on toteutettu vain
ensimmäinen rivi alla olevasta taulukosta.*

## Silmukka ei ole mittarikohtainen

Tämän repon reitti on:

> **rajattu joukko → kielimalli valitsee → deterministinen suoritus →
> tulos + lähdeviite → tai tarkennus / kieltäytyminen**

Mittarit ovat vain täyte. Vaihda katalogi, saat toisen agentin — **sama koodi,
eri sisältö**:

| Agentti | Katalogi sisältää | "Suoritus" tarkoittaa | Lähdeviite |
|---|---|---|---|
| **Mittariagentti** (tämä repo) | mittarimäärittelyt | SQL katalogista | mittari, kaava, rajaus |
| Tarkistusagentti | tarkistussäännöt | sääntöjen ajo | mikä sääntö laukesi, millä arvolla |
| Täsmäytysagentti | täsmäytysparit | kahden luvun erotus | kumpi puoli, mistä lähteestä |
| Poiminta-agentti | sallitut kentät | tekstin poiminta | dokumentti ja sivu |

Väite yhdellä lauseella:

> **Agentti on kolmikko (katalogi, portit, suoritin), jossa kielimalli on ohuin
> ja vaihdettavin osa.**

Agenttien välillä muuttuu **katalogi**. Ei prompt, ei "rooli", ei persoona.
Jos kaksi agenttia eroaa toisistaan vain kehotteen sävyllä, ne ovat sama
agentti kahdesti.

## Lähdeviite on tyyppijärjestelmä, ei kohteliaisuus

Tämä ratkaisee sen, toimiiko useamman agentin ketju lainkaan.

Jos agentti A antaa luvun, joka kantaa mukanaan *"mittari `crew_total_1rm_kg`,
kaava `SUM(one_rm_kg)`, rajaus `challenge = C1`"*, agentti B voi rakentaa sen
päälle **ja tarkistaa, että se sopii yhteen oman rajauksensa kanssa**.

Jos A antaa proosaa, B ei voi tehdä muuta kuin uskoa. Ja usko ei ketjuunnu:
kolmannessa vaiheessa kukaan ei enää tiedä, mitä ensimmäinen luku koski.

Siitä seuraa, että orkestroinnin kuuluu olla **tylsää**: ei agenttien
keskinäistä rupattelua, vaan putki, jossa jokaisen vaiheen tulos on tyypitetty
ja jäljitettävä. Agenttien välinen vapaamuotoinen keskustelu on juuri se kohta,
jossa rajaus ja määritelmä katoavat.

Siksi `nlq/cli.py --json` tulostaa lähdeviitteen koneluettavana. Se ei ole
lisäominaisuus vaan se osa, jonka päälle seuraava vaihe voidaan rakentaa.

## Missä muoto ei päde

Se vaatii, että **toimintajoukko on suljettavissa**.

| Tehtävä | Suljettavissa? |
|---|---|
| "Anna luku X" | Kyllä — mittarilista on äärellinen |
| "Tarkista täsmääkö Y" | Kyllä — sääntölista on äärellinen |
| "Poimi kentät sopimuksesta" | Kyllä — kenttälista on äärellinen |
| **"Analysoi ja kerro mitä tapahtui"** | **Ei.** |

Viimeinen rivi on se, jossa suunnittelu joko muuttuu tai agentti jätetään
tekemättä. Kolmas vaihtoehto — rakentaa se silti ja toivoa — on se, mistä
suurin osa agenttidemoista koostuu.

## Ja yksi tylsä johtopäätös

Kun "tarkistusagenttia" katsoo tarkasti, se on **90-prosenttisesti
tietovarastotesti ja 10-prosenttisesti käännöskerros**:

| Osa | Missä se kuuluu olla |
|---|---|
| *"Onko luku > X?"* / *"täsmääkö summa?"* / *"onko avain uniikki?"* | Testi tietovarastossa. Deterministinen, halpa, ajossa joka kerta. **Ei kielimallia.** |
| *"Miksi tämä poikkeaa, ihmiselle ymmärrettävästi?"* | Käännöskerros — tähän kielimalli on hyvä |
| *"Mitkä ne kaksitoista sääntöä edes ovat?"* | Kielimalli **haastattelijana**, joka kaivaa säännöt asiantuntijasta. Kertaluontoinen, ei ajonaikainen. |
| *"Poikkeama, jota kukaan ei osannut odottaa"* | Tilastollinen menetelmä. Tylsempi ja parempi. |

Vastaus kysymykseen *"miksi tässä ei ole enemmän tekoälyä"*:

> Koska suurin osa siitä, mitä tekoälyltä pyydetään, on IF-lause. Ja IF-lause
> on halvempi, nopeampi ja testattavissa.

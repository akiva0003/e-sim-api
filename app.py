import json
import time
import os
import logging
from werkzeug.exceptions import HTTPException
from datetime import date, timedelta

from flask import Flask, request, jsonify, redirect
from lxml.html import fromstring
import requests
from pymongo import MongoClient

    
client = MongoClient(os.environ['db'])

mycol = client["database"]["collection"]
priceDB = client["database"]["price"]

app = Flask(__name__)
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)


def get_tree(url):
    return fromstring(requests.get(url, timeout=30).text)


def chunker(seq, size):
    return (seq[pos:pos + size] for pos in range(0, len(seq), size))


def camelCase(st):
    output = ''.join(x for x in st.title() if x.isalnum())
    return output[0].lower() + output[1:]


@app.before_request
def save_count():
    api_count = mycol.find_one({"_id": "api count"}, {"_id": 0})
    if "e-sim.org/" in request.full_path:
        link = request.full_path[1:].split("e-sim.org/")[1].split(".html")[0]
    else:
        link = "Index"
    if link not in api_count:
        api_count[link] = 0
    api_count[link] += 1
        
    mycol.replace_one({'_id': "api count"}, dict(sorted(api_count.items(), key=lambda kv: kv[1], reverse=True)))
    

@app.errorhandler(HTTPException)
def handle_exception(e):
    """Return JSON instead of HTML for HTTP errors."""
    # start with the correct headers and status code from the error
    response = e.get_response()
    # replace the body with JSON
    response.data = json.dumps({
        "code": e.code,
        "name": e.name,
        "description": e.description,
    })
    response.content_type = "application/json"
    return response


@app.route('/', methods=['GET'])
@app.route('/index', methods=['GET'])
def home():
    page = '''<!DOCTYPE html>
<html>
<head>
<title>E-sim Unofficial API</title>

<h1>E-sim unofficial API</h1>
<hr>
<h2>Available base links:</h2>
<ul>'''
    links = ["<li>" + str(x).split("e-sim.org/")[1].split(".html")[0] + "</li>" for x in app.url_map.iter_rules() if "e-sim.org" in str(x)]
    links.sort()
    page += "".join(links)
    page += f'''</ul>
<hr>
<h1>Usage:</h1>
<p>Add the following prefix to any of the above pages:
<p><a href={request.base_url}>{request.base_url}</a>
<p><b>Example:</b>
<p><a href={request.base_url}https://alpha.e-sim.org/law.html?id=1>{request.base_url}https://secura.e-sim.org/law.html?id=1</a>
<hr>
<h1>Source Code:</h1>
<p><a href=https://github.com/akiva0003/e-sim-api/blob/main/app.py>GitHub</a>
<hr>
<p><b>Keep in mind that each request takes twice as much as if you would scrape the html by yourself.</b></p>
<hr>
</body>
</html>
'''
    return page


@app.route('/<https>://<server>.e-sim.org/prices.html', methods=['GET'])
def prices(https, server):
    row = priceDB.find_one({"_id": server}, {"_id": 0})
    row["Headers"] = row["Product"][0]
    del row["Product"]
    for product in row:
        if product == "Headers":
            continue
        for num, first_5 in enumerate(row[product]):
            DICT = {}
            for Index, column in enumerate(first_5):
                DICT[row["Headers"][Index].lower()] = column
            try:
                row[product][num] = DICT
            except:
                print(product, num)
                        
    row["last update"] = " ".join(row["Headers"][-1].split()[2:4])
    del row["Headers"]
    return jsonify(row)


@app.route('/<https>://<server>.e-sim.org/statistics.html', methods=['GET'])
def statistics(https, server):
    # locked to registered users.
    return redirect(request.url.replace("statistics.html?selectedSite=" + request.args["selectedSite"],
                                        camelCase(request.args["selectedSite"]) + "Statistics.html").replace("&", "?", 1))


@app.route(f'/<https>://<server>.e-sim.org/article.html', methods=['GET'])
def article(https, server):
    tree = get_tree(f"{request.full_path[1:].replace(f'{https}:/', 'https://')}")
    posted = " ".join(tree.xpath('//*[@class="mobile_article_preview_width_fix"]/text()')[0].split()[1:-1])
    title = tree.xpath('//*[@class="articleTitle"]/text()')[0]
    subs, votes = [int(x.strip()) for x in tree.xpath('//*[@class="bigArticleTab"]/text()')]
    author_name, newspaper_name = tree.xpath('//*[@class="mobileNewspaperStatus"]/a/text()')
    author_id, newspaper_id = [int(x.split("=")[1]) for x in tree.xpath('//*[@class="mobileNewspaperStatus"]/a/@href')[:2]]
    row = {"posted": posted, "title": title, "author": author_name.strip(), "author id": author_id, "votes": votes,
           "newspaper": newspaper_name, "newspaper id": newspaper_id, "subs": subs}
    return jsonify(row)


@app.route('/<https>://<server>.e-sim.org/auction.html', methods=['GET'])
def auction(https, server):
    tree = get_tree(f"{request.full_path[1:].replace(f'{https}:/', 'https://')}")
    seller = tree.xpath("//div[1]//table[1]//tr[2]//td[1]//a/text()")[0]
    buyer = tree.xpath("//div[1]//table[1]//tr[2]//td[2]//a/text()") or ["None"]
    item = tree.xpath("//*[@id='esim-layout']//div[1]//tr[2]//td[3]/b/text()")
    if not item:
        item = [x.strip() for x in tree.xpath("//*[@id='esim-layout']//div[1]//tr[2]//td[3]/text()") if x.strip()]
    price = tree.xpath("//div[1]//table[1]//tr[2]//td[4]//b//text()")[0]
    bidders = int(tree.xpath('//*[@id="esim-layout"]//div[1]//table//tr[2]//td[5]/b')[0].text)
    time1 = tree.xpath('//*[@id="esim-layout"]//div[1]//table//tr[2]//td[6]/span/text()')
    if not time1:
        time1 = [x.strip() for x in tree.xpath('//*[@id="esim-layout"]//div[1]//table//tr[2]//td[6]/text()') if x.strip()]
    else:
        time1 = time1[0].split(":")
        time1 = [f'{int(time1[0]):02d}:{int(time1[1]):02d}:{int(time1[2]):02d}']
    row = {"seller": seller.strip(), "buyer": buyer[0].strip(), "item": item[0],
           "price": float(price) if float(price) != int(float(price)) else int(float(price)), "time": time1[0], "bidders": bidders}
    return jsonify(row)


@app.route('/<https>://<server>.e-sim.org/showShout.html', methods=['GET'])
def showShout(https, server):
    tree = get_tree(f"{request.full_path[1:].replace(f'{https}:/', 'https://')}")
    shout = [x.strip() for x in tree.xpath(f'//*[@class="shoutContainer"]//div//div[1]//text()') if x.strip()]
    shout = "\n".join([x.replace("★", "") for x in shout]).strip()
    author = tree.xpath(f'//*[@class="shoutAuthor"]//a/text()')[0].strip()
    posted = tree.xpath(f'//*[@class="shoutAuthor"]//b')[0].text
    row = {"body": shout, "author": author, "posted": posted.replace("posted ", "")}
    return jsonify(row)


@app.route('/<https>://<server>.e-sim.org/law.html', methods=['GET'])
def law(https, server):
    tree = get_tree(f"{request.full_path[1:].replace(f'{https}:/', 'https://')}")
    time1 = tree.xpath('//*[@id="esim-layout"]//script[3]/text()')[0]
    time1 = [i.split(");\n")[0] for i in time1.split("() + ")[1:]]
    if int(time1[0]) < 0:
        time1 = "Voting finished"
    else:
        time1 = f'{int(time1[0]):02d}:{int(time1[1]):02d}:{int(time1[2]):02d}'
    proposal = " ".join([x.strip() for x in tree.xpath('//table[1]//tr[2]//td[1]//div[2]//text()')]).strip()
    by = tree.xpath('//table[1]//tr[2]//td[3]//a/text()')[0]
    yes = [x.strip() for x in tree.xpath('//table[2]//td[2]//text()') if x.strip()][0]
    no = [x.strip() for x in tree.xpath('//table[2]//td[3]//text()') if x.strip()][0]
    time2 = tree.xpath('//table[1]//tr[2]//td[3]//b')[0].text
    row = {"law proposal": proposal, "proposed by": by.strip(), "proposed": time2,
           "remaining time" if "Voting finished" not in time1 else "status": time1, "yes": int(yes), "no": int(no)}
    return jsonify(row)


@app.route('/<https>://<server>.e-sim.org/congressElections.html', methods=['GET'])
def congressElections(https, server):
    tree = get_tree(f"{request.full_path[1:].replace(f'{https}:/', 'https://')}")
    country = tree.xpath('//*[@id="countryId"]//option[@selected="selected"]')[0].text
    countryId = int(tree.xpath('//*[@id="countryId"]//option[@selected="selected"]/@value')[0])
    date = tree.xpath('//*[@id="date"]//option[@selected="selected"]')[0].text
    candidates = tree.xpath("//tr//td[2]//a/text()")
    candidates_links = [int(x.split("id=")[1]) for x in tree.xpath("//tr//td[2]//a/@href")]
    parties = tree.xpath("//tr//td[4]//div/a/text()")
    parties_links = [int(x.split("id=")[1]) for x in tree.xpath("//tr//td[4]//div/a/@href")]
    votes = [x.replace("-", "0").strip() for x in tree.xpath("//tr[position()>1]//td[5]//text()") if x.strip()] or ["0"] * len(candidates)

    row = {"country": country, "country id": countryId, "date": date, "candidates": []}
    for candidate, candidate_id, vote, party_name, party_id in zip(candidates, candidates_links, votes, parties, parties_links):
        row["candidates"].append({"candidate": candidate.strip(), "candidate id": candidate_id, "votes": int(vote.strip()),
                                  "party name": party_name, "party id": party_id})
    return jsonify(row)


@app.route('/<https>://<server>.e-sim.org/presidentalElections.html', methods=['GET'])
def presidentalElections(https, server):
    tree = get_tree(f"{request.full_path[1:].replace(f'{https}:/', 'https://')}")
    country = tree.xpath('//*[@id="countryId"]//option[@selected="selected"]')[0].text
    countryId = int(tree.xpath('//*[@id="countryId"]//option[@selected="selected"]/@value')[0])
    date = tree.xpath('//*[@id="date"]//option[@selected="selected"]')[0].text
    candidates = tree.xpath("//tr//td[2]//a/text()")
    IDs = [int(x.split("?id=")[1]) for x in tree.xpath("//tr//td[2]//a/@href")]
    votes = [x.replace("-", "0").strip() for x in tree.xpath("//tr[position()>1]//td[4]//text()") if x.strip()] or ["0"] * len(candidates)
    row = {"country": country, "country id": countryId, "date": date, "candidates": []}
    for candidate, vote, id in zip(candidates, votes, IDs):
        row["candidates"].append({"candidate": candidate.strip(), "votes": int(vote.strip()), "candidate id": id})
    return jsonify(row)


@app.route('/<https>://<server>.e-sim.org/battleDrops.html', methods=['GET'])
def battleDrops(https, server):
    tree = get_tree(f"{request.full_path[1:].replace(f'{https}:/', 'https://')}")
    last_page = tree.xpath("//ul[@id='pagination-digg']//li[last()-1]//@href") or ['page=1']
    last_page = int(last_page[0].split('page=')[1])
    row = {"pages": last_page, "drops": []}
    if "showSpecialItems" in request.full_path:
        items = tree.xpath("//tr[position()>1]//td[1]//text()")
        items = [item.strip() for item in items if item.strip()]
        nicks = tree.xpath("//tr[position()>1]//td[2]//a/text()")
        IDs = [int(x.split("?id=")[1]) for x in tree.xpath("//tr[position()>1]//td[2]//a/@href")]
        for nick, item, id in zip(nicks, items, IDs):
            row["drops"].append({"nick": nick.strip(), "item": item.strip(), "citizen id": id})
    else:                            
        Qs = tree.xpath("//td[2]//b/text()")
        items = tree.xpath("//td[3]//b/text()")
        nicks = tree.xpath("//td[4]//a/text()")
        IDs = [int(x.split("?id=")[1]) for x in tree.xpath("//td[4]//a/@href")]
        for nick, Q, item, id in zip(nicks, Qs, items, IDs):
            row["drops"].append({"nick": nick.strip(), "citizen id": id, "item": item.strip(), "quality": int(Q.replace("Q", ""))})
    return jsonify(row)


@app.route('/<https>://<server>.e-sim.org/jobMarket.html', methods=['GET'])
def jobMarket(https, server):
    tree = get_tree(f"{request.full_path[1:].replace(f'{https}:/', 'https://')}")
    country = tree.xpath('//*[@id="countryId"]//option[@selected="selected"]')[0].text
    countryId = int(tree.xpath('//*[@id="countryId"]//option[@selected="selected"]/@value')[0])
    employers = tree.xpath('//*[@id="esim-layout"]//td[1]/a/text()')
    companies = tree.xpath('//*[@id="esim-layout"]//td[2]/a/text()')
    companies_link = tree.xpath('//*[@id="esim-layout"]//td[2]/a/@href')
    company_types = []
    qualities = []
    products = tree.xpath('//*[@id="esim-layout"]//td[3]/div/div/img/@src')
    for p in chunker(products, 2):
        product, quality = [x.split("//cdn.e-sim.org//img/productIcons/")[1].split(".png")[0] for x in p]
        product = product.replace("Defense System", "Defense_System").strip()
        quality = quality.replace("q", "").strip()
        company_types.append(product)
        qualities.append(int(quality))
    skills = tree.xpath('//*[@id="esim-layout"]//tr[position()>1]//td[4]/text()')
    salaries = [float(x) for x in tree.xpath('//*[@id="esim-layout"]//td[5]/b/text()')]
    salaries = [float(x) if float(x) != int(float(x)) else int(float(x)) for x in salaries]
    row = {"country": country, "country id": countryId, "offers": []}
    for employer, company, company_link, company_type, quality, skill, salary in zip(
            employers, companies, companies_link, company_types, qualities, skills, salaries):
        row["offers"].append({"employer": employer.strip(), "company": company, "company id": int(company_link.split("?id=")[1]),
                              "company type": company_type, "company quality": int(quality),
                              "minimal skill": int(skill), "salary": salary if salary != int(salary) else int(salary)})
    row["cc"] = tree.xpath('//*[@id="esim-layout"]//tr[2]//td[5]/text()')[-1].strip() if row["offers"] else ""
    return jsonify(row)


@app.route('/<https>://<server>.e-sim.org/newCitizens.html', methods=['GET'])
def newCitizens(https, server):
    tree = get_tree(f"{request.full_path[1:].replace(f'{https}:/', 'https://')}")
    country = tree.xpath('//*[@id="countryId"]//option[@selected="selected"]')[0].text
    countryId = int(tree.xpath('//*[@id="countryId"]//option[@selected="selected"]/@value')[0])
    nicks = tree.xpath('//td[1]/a/text()')
    levels = tree.xpath('//tr[position()>1]//td[2]/text()')
    experiences = tree.xpath('//tr[position()>1]//td[3]/text()')
    registered = tree.xpath('//tr[position()>1]//td[4]/text()')
    locations = tree.xpath('//tr[position()>1]//td[5]/a/text()')
    location_links = tree.xpath('//td[5]/a/@href')
    links = tree.xpath("//td[1]/a/@href")
    row = {"country": country, "country id": countryId, "new citizens": []}
    for nick, level, experience, registered, location, location_link, link in zip(
            nicks, levels, experiences, registered, locations, location_links, links):
        row["new citizens"].append(
            {"nick": nick, "level": int(level.strip()), "experience": int(experience.strip()),
             "registered": registered.strip(), "region": location, "location id": int(location_link.split("?id=")[1]),
             "citizen id": int(link.split("?id=")[1])})
    return jsonify(row)


@app.route('/<https>://<server>.e-sim.org/region.html', methods=['GET'])
def region(https, server):
    tree = get_tree(f"{request.full_path[1:].replace(f'{https}:/', 'https://')}")
    owner = tree.xpath('//*[@id="esim-layout"]//div[1]//tr[2]//td[1]//span')[0].text
    rightful_owner = tree.xpath('//*[@id="esim-layout"]//div[1]//tr[2]//td[2]//span')[0].text
    region_name = tree.xpath('//*[@id="esim-layout"]//h1')[0].text.replace("Region ", "")
    try:
        resource_type = tree.xpath('//*[@id="esim-layout"]//div[1]//tr[2]//td[3]/div/div/img/@src')[0].split("//cdn.e-sim.org//img/productIcons/")[1].split(".png")[0]
    except:
        resource_type = "No resources"
    resource = tree.xpath('//*[@id="esim-layout"]//div[1]//tr[2]//td[3]/b')
    resource = resource[0].text if resource else "No resources"
    population = tree.xpath('//*[@id="esim-layout"]//div[1]//tr[2]//td[4]/b')[0].text
    active_companies, all_companies = tree.xpath('//*[@id="esim-layout"]//div[1]//tr[2]//td[5]/b')[0].text.split()

    is_occupied = tree.xpath('//*[@id="esim-layout"]//div[2]//b[1]/text()')
    base_div = 3 if len(is_occupied) == 1 else 2
    industry = tree.xpath(f'//*[@id="esim-layout"]//div[{base_div}]//table[1]//b[1]/text()')
    industry = dict(zip(industry[::2], [float(x) if float(x) != int(float(x)) else int(float(x)) for x in industry[1::2]]))
    companies_type = tree.xpath('//*[@id="esim-layout"]//table[2]//td[1]/b/text()')
    total_companies = [x.strip() for x in tree.xpath('//*[@id="esim-layout"]//table[2]//tr[position()>1]//td[2]/text()') if x.strip()]
    values = tree.xpath('//*[@id="esim-layout"]//table[2]//td[3]/b/text()')
    values = [float(x) if float(x) != int(float(x)) else int(float(x)) for x in values]                
    penalties = tree.xpath('//*[@id="esim-layout"]//table[2]//tr[position()>1]//td[4]/text()') or ["100%"] * len(values)

    active = {}
    for company_type, total_companies, value, penalty in zip(companies_type, total_companies, values, penalties):
        active[company_type] = {"total companies": int(total_companies.strip()), "value": value, "penalty": penalty.strip()}

    rounds = tree.xpath('//*[@id="esim-layout"]//table[2]//td[2]/b/text()')
    buildings = tree.xpath('//*[@id="esim-layout"]//table[2]//td[1]/div/div/img/@src')
    building_places = {}
    for Round, p in zip(rounds, chunker(buildings, 2)):
        building, quality = [x.split("//cdn.e-sim.org//img/productIcons/")[1].split(".png")[0] for x in p]
        building = building.replace("Defense System", "Defense_System").strip()
        building_places[int(Round)] = f"{quality.strip().upper()} {building}"

    row = {"region": region_name, "active companies stats": active, "buildings": [{"round": k, "building": v} for k, v in building_places.items()],
           "industry": [{"company": k, "total value": v} for k, v in industry.items()], "current owner": owner,
           "rightful owner": rightful_owner, "resource": resource_type, "resource richness": resource, "population": int(population),
           "active companies": int(active_companies), "total companies": int(all_companies.replace("(", "").replace(")", ""))}
    return jsonify(row)


@app.route('/<https>://<server>.e-sim.org/monetaryMarket.html', methods=['GET'])
def monetaryMarket(https, server):
    tree = get_tree(f"{request.full_path[1:].replace(f'{https}:/', 'https://')}")
    buy = tree.xpath('//*[@id="buy"]//option[@selected="selected"]')[0].text
    sell = tree.xpath('//*[@id="sell"]//option[@selected="selected"]')[0].text 
    seller = tree.xpath("//td[1]/a/text()")
    links = [int(x.split("?id=")[1]) for x in tree.xpath("//td[1]/a/@href")]
    amount = tree.xpath("//td[2]/b/text()")
    amount = [float(x) if float(x) != int(float(x)) else int(float(x)) for x in amount]    
    ratio = tree.xpath("//td[3]/b/text()")
    ratio = [float(x) if float(x) != int(float(x)) else int(float(x)) for x in ratio]   
    IDs = [int(x.value) for x in tree.xpath("//td[4]//form//input[2]")]
    row = {"buy": buy, "sell": sell, "offers": []}
    for seller, link, amount, ratio, id in zip(seller, links, amount, ratio, IDs):
        row["offers"].append({"seller": seller.strip(), "seller id": link, "amount": amount, "ratio": ratio, "offer id": id})
    return jsonify(row)


@app.route('/<https>://<server>.e-sim.org/stockCompany.html', methods=['GET'])
def stockCompany(https, server):
    tree = get_tree(f"{request.full_path[1:].replace(f'{https}:/', 'https://')}")
    MAIN = [float(tree.xpath(f'//*[@id="esim-layout"]//div[1]//tr//td[2]//div[2]/b[{b}]/text()')[0]) for b in range(1, 7)]
    MAIN = [int(x) if int(x) == float(x) else float(x) for x in MAIN]
    try:
        price = tree.xpath('//*[@id="esim-layout"]//tr//td[2]//div[1]//table[1]//td[2]/b/text()')
        price = [float(x) for x in price]
        stock = tree.xpath('//*[@id="esim-layout"]//tr//td[2]//div[1]//table[1]//td[1]/b/text()')
        stock = [int(x) for x in stock]
    except:
        price, stock = [], []
    offers = [{"amount": stock, "price": price} for stock, price in zip(stock, price)]
    try:        
        last_transactions_amount = tree.xpath('//*[@id="esim-layout"]//tr//td[2]//div[1]//table[3]//td[1]/b/text()')
        last_transactions_price = tree.xpath('//*[@id="esim-layout"]//tr//td[2]//div[1]//table[3]//td[2]/b/text()')
        last_transactions_time = tree.xpath('//*[@id="esim-layout"]//tr//td[2]//div[1]//table[3]//tr[position()>1]//td[3]/text()')        
    except:
        last_transactions_amount, last_transactions_price, last_transactions_time = [], [], []
    header = ["total shares", "total value", "price per share", "daily trade value", "shareholders", "companies", "offers", "shares for sell"]
    last_transactions = [{"amount": int(a.strip()), "price": float(b.strip()), "time": c.strip()} for a, b, c in zip(
        last_transactions_amount, last_transactions_price, last_transactions_time)]
    row = {header: value for header, value in zip(header, MAIN + [offers] + [last_transactions])}
    return jsonify(row)


@app.route('/<https>://<server>.e-sim.org/stockCompanyProducts.html', methods=['GET'])
def stockCompanyProducts(https, server):
    tree = get_tree(f"{request.full_path[1:].replace(f'{https}:/', 'https://')}")
    row = {}    
    amount = [int(x.strip()) for x in tree.xpath('//*[@id="esim-layout"]//center//div//div//div[1]/text()')]
    products = [x.split("//cdn.e-sim.org//img/productIcons/")[1].split(".png")[0] for x in tree.xpath('//*[@id="esim-layout"]//center//div//div//div[2]//img[1]/@src')]
    for Index, product in enumerate(products):        
        quality = tree.xpath(f'//*[@id="esim-layout"]//center//div//div[{Index+1}]//div[2]//img[2]/@src')
        if "Defense System" in product:
            product = product.replace("Defense System", "Defense_System")
        if quality:
            products[Index] = f'{quality[0].split("//cdn.e-sim.org//img/productIcons/")[1].split(".png")[0].upper()} {product}'
    row["storage"] = [{"product": product, "amount": amount} for product, amount in zip(products, amount)]

    amount = [int(x.strip()) for x in tree.xpath('//*[@id="esim-layout"]//div[2]//table//tr//td[3]/text()')[1:]]
    gross_price = [float(x) for x in tree.xpath(f'//*[@id="esim-layout"]//div[2]//table//tr//td[4]/b/text()')]
    gross_price = [float(x) if float(x) != int(x) else int(x) for x in gross_price]    
    coin = [x.strip() for x in tree.xpath(f'//*[@id="esim-layout"]//div[2]//table//tr//td[4]/text()')[1:] if x.strip()]
    net_price = [float(x) for x in tree.xpath(f'//*[@id="esim-layout"]//div[2]//table//tr//td[5]/b/text()')]
    net_price = [float(x) if float(x) != int(x) else int(x) for x in net_price]  
    products = [x.split("//cdn.e-sim.org//img/productIcons/")[1].split(".png")[0] for x in tree.xpath('//*[@id="esim-layout"]//div[2]//table//tr//td[1]//img[1]/@src')]
    for Index, product in enumerate(products):        
        quality = tree.xpath(f'//*[@id="esim-layout"]//div[2]//table//tr[{Index+2}]//td[1]//img[2]/@src')
        if "Defense System" in product:
            product = product.replace("Defense System", "Defense_System")
        if quality:
            products[Index] = f'{quality[0].split("//cdn.e-sim.org//img/productIcons/")[1].split(".png")[0].upper()} {product}'
    row["offers"] = []
    for product, amount, gross_price, coin, net_price in zip(products, amount, gross_price, coin, net_price):
        row["offers"].append({"product": product, "amount": amount, "gross price": gross_price, "coin": coin, "net price": net_price})
    return jsonify(row)


@app.route('/<https>://<server>.e-sim.org/stockCompanyMoney.html', methods=['GET'])
def stockCompanyMoney(https, server):
    tree = get_tree(f"{request.full_path[1:].replace(f'{https}:/', 'https://')}")
    cc = tree.xpath(f'//*[@id="esim-layout"]//div[2]//div/text()')
    cc = [c.strip() for c in cc if c.strip()]
    cc1 = tree.xpath(f'//*[@id="esim-layout"]//div[2]//div/b/text()')
    cc1 = [float(x) if float(x) != int(float(x)) else int(float(x)) for x in cc1]    
    row = {"storage": {k: v for k, v in zip(cc, cc1)}}
    amount = tree.xpath(f'//*[@id="esim-layout"]//div[3]//table//tr/td[2]/b/text()')
    amount = [float(x) if float(x) != int(float(x)) else int(float(x)) for x in amount]    
    coin = [x.strip() for x in tree.xpath(f'//*[@id="esim-layout"]//div[3]//table//tr/td[2]/text()') if x.strip()][1:]
    ratio = tree.xpath(f'//*[@id="esim-layout"]//div[3]//table//tr/td[3]/b/text()')
    ratio = [float(x) if float(x) != int(float(x)) else int(float(x)) for x in ratio]   
    IDs = [int(x.value) for x in tree.xpath(f'//*[@id="esim-layout"]//div[3]//table//tr/td[4]//form//input[2]')]
    row["offers"] = [{"amount": amount, "coin": coin, "ratio": ratio, "id": id} for amount, coin, ratio, id in zip(
        amount, coin, ratio, IDs)]
    return jsonify(row)


@app.route('/<https>://<server>.e-sim.org/achievement.html', methods=['GET'])
def achievement(https, server):
    tree = get_tree(f"{request.full_path[1:].replace(f'{https}:/', 'https://')}")
    last_page = tree.xpath("//ul[@id='pagination-digg']//li[last()-1]//@href") or ['page=1']
    last_page = int(last_page[0].split('page=')[1])
    links = [x.split("?id=")[1] for x in tree.xpath(f'//*[@id="esim-layout"]//div[3]//div/a/@href')]
    nicks = [x.strip() for x in tree.xpath(f'//*[@id="esim-layout"]//div[3]//div/a/text()')]
    category, achieved_by = [x.split(":")[1].strip() for x in tree.xpath(f'//*[@id="esim-layout"]//div[1]//div[2]/text()') if x.strip()]
    row = {"category": category, "achieved by": achieved_by, "links": links, "nicks": nicks, "pages": last_page}
    return jsonify(row)


@app.route('/<https>://<server>.e-sim.org/countryEconomyStatistics.html', methods=['GET'])
def countryEconomyStatistics(https, server):
    tree = get_tree(f"{request.full_path[1:].replace(f'{https}:/', 'https://')}")
    country = tree.xpath('//*[@id="countryId"]//option[@selected="selected"]')[0].text
    countryId = int(tree.xpath('//*[@id="countryId"]//option[@selected="selected"]/@value')[0]) 
    links = [int(x.split("id=")[1]) for x in tree.xpath('//*[@id="esim-layout"]//table[1]//td[1]/a/@href')]
    regions = tree.xpath('//*[@id="esim-layout"]//table[1]//td[1]/a/text()')
    regions = {k: v for k, v in zip(links, regions)}
    population = [x.strip().replace(":", "").lower() for x in tree.xpath('//*[@id="esim-layout"]//div[2]//table//tr//td/text()') if x.strip()]
    minimal_salary = tree.xpath('//*[@id="esim-layout"]//div[2]//table//tr[6]//td[2]/b')[0].text
    population[-1] = minimal_salary
    population = dict(zip(population[::2], [float(x) if float(x) != int(float(x)) else int(float(x)) for x in population[1::2]]))
    treasury_keys = [x.strip() for x in tree.xpath('//*[@id="esim-layout"]//table[3]//tr[position()>1]//td/text()') if x.strip()]
    treasury_values = tree.xpath('//*[@id="esim-layout"]//table[3]//tr[position()>1]//td/b/text()')
    treasury = {k: float(v) for k, v in zip(treasury_keys, treasury_values)}
    table = tree.xpath('//*[@id="esim-layout"]//table[2]//tr//td/text()')
    table = [x.strip() for x in table]
    taxes = {table[4:][i]: table[4:][i+1:i+4] for i in range(0, len(table[4:])-4, 4)}
    for k, v in taxes.items():
        taxes[k] = {key: val for key, val in zip(table[1:4], v)}
    row = {"country": country, "country id": countryId, "borders": regions, "treasury": treasury, "taxes": taxes}
    row.update(population)    
    return jsonify(row)


@app.route('/<https>://<server>.e-sim.org/stockCompanyStatistics.html', methods=['GET'])
@app.route('/<https>://<server>.e-sim.org/citizenStatistics.html', methods=['GET'])
def citizenStatistics(https, server):
    tree = get_tree(f"{request.full_path[1:].replace(f'{https}:/', 'https://')}")
    country = tree.xpath('//*[@id="countryId"]//option[@selected="selected"]')[0].text
    try:
        statistic_type = tree.xpath('//*[@name="statisticType"]//option[@selected="selected"]')[0].text
    except:
        statistic_type = tree.xpath('//*[@name="statisticType"]//option[1]')[0].text
    countryId = int(tree.xpath('//*[@id="countryId"]//option[@selected="selected"]/@value')[0])
    links = tree.xpath("//td/a/@href")
    nicks = tree.xpath("//td/a/text()")
    countries = tree.xpath("//td[3]/b/text()")
    values = tree.xpath("//tr[position()>1]//td[4]/text()") if "citizenStatistics" in request.full_path else tree.xpath("//tr[position()>1]//td[4]/b/text()")
    for Index, parameter in enumerate(values):
        value = ""
        for char in parameter:
            if char in "1234567890.":
                value += char
        if value:
            values[Index] = int(float(value)) if int(float(value)) == float(value) else float(value)

    row = {"country": country, "country id": countryId, "statistic type": statistic_type,
           "citizens" if "citizenStatistics" in request.full_path else "stock companies": [
               {"id": int(link.split("id=")[1]), "nick" if "citizenStatistics" in request.full_path else "stock company": nick.strip(),
                         "country": country, "value": value} for link, nick, country, value in zip(links, nicks, countries, values)]}
    return jsonify(row)


@app.route('/<https>://<server>.e-sim.org/countryStatistics.html', methods=['GET'])
def countryStatistics(https, server):
    tree = get_tree(f"{request.full_path[1:].replace(f'{https}:/', 'https://')}")
    statistic_type = tree.xpath('//*[@name="statisticType"]//option[@selected="selected"]')[0].text
    countries = tree.xpath("//td/b/text()")[1:]
    values = tree.xpath("//td[3]/text()")[1:]
    row = {"statistic type": statistic_type,
           "countries": [{"country": k, "value": int(v.strip())} for k, v in zip(countries, values)]}
    return jsonify(row)


@app.route('/<https>://<server>.e-sim.org/coalitionStatistics.html', methods=['GET'])
def coalitionStatistics(https, server):
    tree = get_tree(f"{request.full_path[1:].replace(f'{https}:/', 'https://')}")
    row = []
    for tr in range(2, 103):  # First 100
        try:
            id = int(tree.xpath(f'//tr[{tr}]//td[1]//span')[0].text)
            name = tree.xpath(f'//tr[{tr}]//td[2]//span/text()') or ["-"]
            leader = tree.xpath(f'//tr[{tr}]//td[3]/a/text()') or ["-"]
            leader_id = [int(x.split("?id=")[1]) for x in tree.xpath(f'//tr[{tr}]//td[3]/a/@href')] or [0]
            members = int(tree.xpath(f'//tr[{tr}]//td[4]//span')[0].text)
            regions = int(tree.xpath(f'//tr[{tr}]//td[5]//span')[0].text)
            citizens = int(tree.xpath(f'//tr[{tr}]//td[6]//span')[0].text)
            dmg = int(tree.xpath(f'//tr[{tr}]//td[7]//span')[0].text.replace(",", ""))
            row.append({"id": id, "name": name[0], "leader": leader[0].strip(), "leader id": leader_id[0],
                        "members": members, "regions": regions, "citizens": citizens, "dmg": dmg})
        except:
            break
    row = sorted(row, key=lambda k: k['dmg'], reverse=True)
    return jsonify(row)


@app.route('/<https>://<server>.e-sim.org/newCitizenStatistics.html', methods=['GET'])
def newCitizenStatistics(https, server):
    tree = get_tree(f"{request.full_path[1:].replace(f'{https}:/', 'https://')}")
    names = [x.strip() for x in tree.xpath("//tr//td[1]/a/text()")]
    ids = [int(x.split("?id=")[1]) for x in tree.xpath("//tr//td[1]/a/@href")]
    countries = tree.xpath("//tr//td[2]/span/text()")
    registration_time = [x.strip() for x in tree.xpath("//tr[position()>1]//td[3]/text()[1]")]
    registration_time1 = tree.xpath("//tr//td[3]/text()[2]")
    xp = [int(x) for x in tree.xpath("//tr[position()>1]//td[4]/text()")]
    wep = ["v" if "479" in x else "x" for x in tree.xpath("//tr[position()>1]//td[5]/i/@class")]
    food = ["v" if "479" in x else "x" for x in tree.xpath("//tr[position()>1]//td[6]/i/@class")]
    gift = ["v" if "479" in x else "x" for x in tree.xpath("//tr[position()>1]//td[5]/i/@class")]
    row = []
    for name, id, country, registration_time, registration_time1, xp, wep, food, gift in zip(
            names, ids, countries, registration_time, registration_time1, xp, wep, food, gift):
        row.append({"name": name, "id": id, "country": country, "registration time": registration_time,
                    "registered": registration_time1[1:-1], "xp": xp, "wep": wep, "food": food, "gift": gift})
    return jsonify(row)


@app.route('/<https>://<server>.e-sim.org/partyStatistics.html', methods=['GET'])
def partyStatistics(https, server):
    tree = get_tree(f"{request.full_path[1:].replace(f'{https}:/', 'https://')}")
    country = tree.xpath("//tr//td[2]/b/text()")[:50]
    party_name = tree.xpath("//tr//td[3]//div/a/text()")[:50]
    party_id = [int(x.split("?id=")[1]) for x in tree.xpath("//tr//td[3]//div/a/@href")][:50]
    prestige = [int(x) for x in tree.xpath("//tr[position()>1]//td[4]/text()")][:50]
    elected_cps = [int(x.strip()) if x.strip() else 0 for x in tree.xpath("//tr[position()>1]//td[5]/text()")][:50]
    elected_congress = [int(x.strip()) if x.strip() else 0 for x in tree.xpath("//tr[position()>1]//td[6]/text()")][:50]
    laws = [int(x.strip()) if x.strip() else 0 for x in tree.xpath("//tr[position()>1]//td[7]/text()")][:50]
    members = [int(x) for x in tree.xpath("//tr//td[8]/b/text()")][:50]
    row = []
    for country, party_name, party_id, prestige, elected_cps, elected_congress, laws, members in zip(
            country, party_name, party_id, prestige, elected_cps, elected_congress, laws, members):
        row.append({"country": country, "party": party_name, "party id": party_id, "prestige": prestige, "elected cps": elected_cps,
                    "elected congress": elected_congress, "laws": laws, "members": members})
    return jsonify(row)


@app.route('/<https>://<server>.e-sim.org/newspaperStatistics.html', methods=['GET'])
def newspaperStatistics(https, server):
    tree = get_tree(f"{request.full_path[1:].replace(f'{https}:/', 'https://')}")
    last_page = tree.xpath("//ul[@id='pagination-digg']//li[last()-1]//@href") or ['page=1']
    last_page = int(last_page[0].split('page=')[1])
    row = {"pages": last_page, "newspapers": []}
    
    Index = [int(x.strip()) for x in tree.xpath("//tr[position()>1]//td[1]/text()")]
    redactor = [x.strip() for x in tree.xpath("//tr//td[2]/a/text()")]
    redactor_id = [int(x.split("?id=")[1]) for x in tree.xpath("//tr//td[2]/a/@href")]
    newspaper_name = tree.xpath("//tr//td[3]/span/a/text()")
    newspaper_id = [int(x.split("?id=")[1]) for x in tree.xpath("//tr//td[3]/span/a/@href")]
    subs = [int(x) for x in tree.xpath("//tr[position()>1]//td[4]/b/text()")]
    for Index, redactor, redactor_id, newspaper_name, newspaper_id, subs in zip(
            Index, redactor, redactor_id, newspaper_name, newspaper_id, subs):
        row["newspapers"].append({"index": Index, "redactor": redactor, "redactor id": redactor_id,
                                  "newspaper": newspaper_name, "newspaper id": newspaper_id, "subs": subs})
    return jsonify(row)


@app.route('/<https>://<server>.e-sim.org/news.html', methods=['GET'])
def news(https, server):
    tree = get_tree(f"{request.full_path[1:].replace(f'{https}:/', 'https://')}")
    country = tree.xpath('//*[@id="country"]//option[@selected="selected"]')[0].text
    countryId = int(tree.xpath('//*[@id="country"]//option[@selected="selected"]/@value')[0])
    news_type = tree.xpath('//*[@id="newsType"]//option[@selected="selected"]')[0].text
    votes = [int(x.strip()) for x in tree.xpath('//tr//td//div[1]/text()') if x.strip()]
    titles = tree.xpath('//tr//td//div[2]/a/text()')
    links = [int(x.split("?id=")[1]) for x in tree.xpath('//tr//td//div[2]/a/@href')]
    posted = tree.xpath('//tr//td//div[2]//text()[preceding-sibling::br]')
    types, posted = [x.replace("Article type: ", "").strip() for x in posted[1::2]], [x.replace("Posted", "").strip() for x in posted[::2]]
    newspaper_names = [x.strip() for x in tree.xpath('//*[@id="esim-layout"]//table//tr//td//div[3]//div/a[1]/text()')]
    newspaper_id = [int(x.split("?id=")[1]) for x in tree.xpath('//*[@id="esim-layout"]//table//tr//td//div[3]//div/a[1]/@href')]
    row = {"country": country, "country id": countryId, "news type": news_type, "articles": []}
    for title, link, vote, posted, Type, newspaper_name, newspaper_id in zip(
            titles, links, votes, posted, types, newspaper_names, newspaper_id):
        row["articles"].append({"title": title, "article id": link, "votes": vote, "posted": posted, "type": Type, "newspaper name": newspaper_name, "newspaper id": newspaper})
    return jsonify(row)


@app.route('/<https>://<server>.e-sim.org/events.html', methods=['GET'])
def events(https, server):
    tree = get_tree(f"{request.full_path[1:].replace(f'{https}:/', 'https://')}")
    last_page = tree.xpath("//ul[@id='pagination-digg']//li[last()-1]//@href") or ['page=1']
    last_page = int(last_page[0].split('page=')[1])
    country = tree.xpath('//*[@id="country"]//option[@selected="selected"]')[0].text
    countryId = int(tree.xpath('//*[@id="country"]//option[@selected="selected"]/@value')[0])
    events_type = tree.xpath('//*[@id="eventsType"]//option[@selected="selected"]')[0].text
    titles = [x.text_content().replace("\n\xa0 \xa0 \xa0 \xa0", "").replace("  ", " ").strip() for x in tree.xpath('//tr//td//div[2]')]
    titles = [x for x in titles if x]
    icons = [x.split("/")[-1].replace("Icon.png", "") for x in tree.xpath('//tr//td//div[1]//img//@src')]
    icons = [x if ".png" not in x else "" for x in icons]
    links = tree.xpath('//tr//td//div[2]/a/@href')
    row = {"country": country, "country id": countryId, "pages": last_page, "events type": events_type, "events": []}
    for title, link, icon in zip(titles, links, icons):
        row["events"].append({"event": " ".join(title.split("  ")[:-1]).strip(), "time": title.split("  ")[-1].strip(), "link": link, "icon": icon})
    return jsonify(row)


@app.route('/<https>://<server>.e-sim.org/companiesForSale.html', methods=['GET'])
def companiesForSale(https, server):
    tree = get_tree(f"{request.full_path[1:].replace(f'{https}:/', 'https://')}")
    links = [int(x.split("?id=")[1]) for x in tree.xpath('//tr//td[1]//a/@href')]
    company_name = [x.strip() for x in tree.xpath('//tr//td[1]/a/text()')]
    company_types = []
    qualities = []
    products = tree.xpath('//tr//td[2]//div//div//img/@src')
    for p in chunker(products, 2):
        product, quality = [x.split("//cdn.e-sim.org//img/productIcons/")[1].split(".png")[0] for x in p]
        product = product.replace("Defense System", "Defense_System").strip()
        quality = quality.replace("q", "").strip()
        company_types.append(product)
        qualities.append(int(quality))
    location_name = tree.xpath('//tr//td[3]/b/a/text()')
    country = tree.xpath('//tr//td[3]/span[last()]/text()')
    location_link = [int(x.split("?id=")[1]) for x in tree.xpath('//tr//td[3]//a/@href')]
    seller_id = [int(x.split("?id=")[1]) for x in tree.xpath('//tr//td[4]//a/@href')]
    seller_name = [x.replace("\xa0", "") for x in tree.xpath('//tr//td[4]//a/text()')]
    seller_type = tree.xpath('//tr//td[4]//b/text()')
    price = [float(x.replace(" Gold", "")) for x in tree.xpath('//tr//td[5]//b/text()')]
    price = [float(x) if float(x) != int(x) else int(x) for x in price]    
    IDs = [int(x.value) for x in tree.xpath('//tr//td[6]//input[1]')]
    row = []
    for links, company_name, company_types, qualities, location_name, country, location_link, seller_id, seller_name, seller_type, price, IDs in zip(
            links, company_name, company_types, qualities, location_name, country, location_link, seller_id, seller_name, seller_type, price, IDs):
        row.append({"company id": links, "company name": company_name, "company type": company_types, "quality": qualities, "location name": location_name,
                    "country": country, "location id": location_link, "seller id": seller_id, "seller name": seller_name,
                    "seller type": seller_type, "price": price, "offer id": IDs})
    return jsonify(row)


@app.route('/<https>://<server>.e-sim.org/countryPoliticalStatistics.html', methods=['GET'])
def countryPoliticalStatistics(https, server):
    tree = get_tree(f"{request.full_path[1:].replace(f'{https}:/', 'https://')}")
    row = {}
    for minister in ["Defense", "Finance", "Social"]:
        ministry = tree.xpath(f'//*[@id="ministryOf{minister}"]//div//div[2]/a[1]/text()')
        try:
            link = int(tree.xpath(f'//*[@id="ministryOf{minister}"]//div//div[2]/a[1]/@href')[0].split("?id=")[1])
        except:
            continue
        row["minister of "+minister.lower()] = {"id": link, "nick": ministry[0]}

    congress = tree.xpath('//*[@id="congressByParty"]//a/text()')
    congress_links = [int(x.split("?id=")[1]) for x in tree.xpath('//*[@id="congressByParty"]//a/@href')]
    row["congress"] = [{"nick": congress, "id": link} for congress, link in zip(congress, congress_links)]
    coalition = tree.xpath('//*[@id="mobileCountryPoliticalStats"]/span/text()')
    row["coalition members"] = coalition
    sides = [x.replace("xflagsMedium xflagsMedium-", "").replace("-", " ") for x in tree.xpath('//table[1]//tr//td//div//div//div//div//div/@class')]
    sides = [sides[x:x+2] for x in range(0, len(sides), 2)]
    links = tree.xpath('//table[1]//tr//td[2]/a/@href')
    row["wars"] = [{"link": link, "attacker": attacker, "defender": defender} for link, (attacker, defender) in zip(links, sides)]
    naps = tree.xpath('//table[2]//tr//td/b/text()')
    naps_expires = [x.strip() for x in tree.xpath('//table[2]//tr//td[2]/text()')][1:]
    row["naps"] = [{"country": naps, "expires": naps_expires} for naps, naps_expires in zip(naps, naps_expires)]
    allies = tree.xpath('//table[3]//tr//td/b/text()')
    expires = [x.strip() for x in tree.xpath('//table[3]//tr//td[2]/text()')][1:]
    row["mpps"] = [{"country": allies, "expires": expires} for allies, expires in zip(allies, expires)]
    return jsonify(row)


@app.route('/<https>://<server>.e-sim.org/newspaper.html', methods=['GET'])
def newspaper(https, server):
    tree = get_tree(f"{request.full_path[1:].replace(f'{https}:/', 'https://')}")
    titles = tree.xpath('//*[@id="esim-layout"]//table//tr//td//div[2]//a[1]/text()')
    links = [int(x.split("?id=")[1]) for x in tree.xpath('//*[@id="esim-layout"]//table//tr//td//div[2]//a[1]/@href')]
    posted = [x.replace("Posted ", "").strip() for x in tree.xpath('//*[@id="esim-layout"]//table//tr//td//div[2]/text()') if x.strip()]
    votes = [int(x) for x in tree.xpath('//*[@id="esim-layout"]//table//tr//td//div[1]/text()')]
    last_page = tree.xpath("//ul[@id='pagination-digg']//li[last()-1]//@href") or ['page=1']
    last_page = int(last_page[0].split('page=')[1])
    subs = int(tree.xpath('//*[@id="mobileNewspaperStatusContainer"]//div[3]//div/text()')[0].strip())
    redactor = tree.xpath('//*[@id="mobileNewspaperStatusContainer"]/div[1]/a/text()')[0].strip()
    redactor_id = int(tree.xpath('//*[@id="mobileNewspaperStatusContainer"]/div[1]//a/@href')[0].split("profile.html?id=")[-1])
    row = {"subs": subs, "pages": last_page, "redactor": redactor, "redactor id": redactor_id,
           "articles": [{"title": title, "id": id, "posted": posted, "votes": votes} for title, id, posted, votes in zip(titles, links, posted, votes)]}
    return jsonify(row)


@app.route('/<https>://<server>.e-sim.org/party.html', methods=['GET'])
def party(https, server):
    tree = get_tree(f"{request.full_path[1:].replace(f'{https}:/', 'https://')}")
    name = tree.xpath('//*[@id="unitStatusHead"]//div/a/text()')[0]
    country = tree.xpath('//*[@id="partyContainer"]//table//tr//td[2]//div[1]//table//tr//td[2]//div//b//span/text()')[0]
    MAIN = [x.strip() for x in tree.xpath('//*[@id="partyContainer"]//table//tr//td[2]//div[1]//table//tr//td[2]//div//b/text()') if x.strip()]
    headers = [x.strip() for x in tree.xpath('//*[@id="partyContainer"]//table//tr//td[2]//div[1]//table//tr//td[1]//div//b/text()') if x.strip()][1:]
    row = {"members": [], "country": country, "name": name}
    for k, v in zip(headers, MAIN):
        if k == "Members":
            k = "members count"
        try:
            v = int(v.replace(",", ""))
        except:
            v = v
        row[k] = v
    nicks = tree.xpath('//*[@id="mobilePartyMembersWrapper"]//div[1]/a/text()')
    links = [int(x.split("?id=")[1]) for x in tree.xpath('//*[@id="mobilePartyMembersWrapper"]//div[1]/a/@href')]
    joined = tree.xpath('//*[@id="mobilePartyMembersWrapper"]//div[2]/i/text()')
    for Index, (nick, id, joined) in enumerate(zip(nicks, links, joined)):
        icons = tree.xpath(f'//*[@id="mobilePartyMembersWrapper"][{Index+1}]//div[1]//i/@title')
        if icons and "Party Leader" in icons[0]:
            icons[0] = icons[0].replace("Party Leader", "")
            icons.insert(0, "Party Leader")
        row["members"].append({"nick": nick.strip(), "id": id, "joined": joined, "roles": icons})
    return jsonify(row)


@app.route('/<https>://<server>.e-sim.org/productMarket.html', methods=['GET'])
def productMarket(https, server):
    tree = get_tree(f"{request.full_path[1:].replace(f'{https}:/', 'https://')}")
    last_page = tree.xpath("//ul[@id='pagination-digg']//li[last()-1]//@href") or ['page=1']
    last_page = int(last_page[0].split('page=')[1])

    products = [x.split("//cdn.e-sim.org//img/productIcons/")[1].split(".png")[0] for x in
                tree.xpath(f'//*[@id="productMarketItems"]//tr//td[1]//img[1]/@src')]
    for Index, product in enumerate(products):
        quality = tree.xpath(f'//*[@id="productMarketItems"]//tr[{Index + 2}]//td[1]//img[2]/@src')
        if "Defense System" in product:
            product = product.replace("Defense System", "Defense_System")
        if quality:
            products[
                Index] = f'{quality[0].split("//cdn.e-sim.org//img/productIcons/")[1].split(".png")[0].upper()} {product}'

    ids = [int(x.split("?id=")[1]) for x in tree.xpath('//tr//td[2]//a/@href')]
    seller = [x.strip() for x in tree.xpath('//tr//td[2]//a/text()')]
    price = [float(x) if float(x) != int(float(x)) else int(float(x)) for x in
             tree.xpath(f"//tr[position()>1]//td[4]/b/text()")]
    cc = [x.strip() for x in tree.xpath(f"//tr[position()>1]//td[4]/text()") if x.strip()]
    stock = [int(x.strip()) for x in tree.xpath(f"//tr[position()>1]//td[3]/text()")]
    row = {"pages": last_page, "offers": []}
    for id, seller, product, cc, price, stock in zip(ids, seller, products, cc, price, stock):
        row["offers"].append(
            {"seller": seller, "seller id": id, "product": product, "coin": cc, "price": price, "stock": stock})

    return jsonify(row)


@app.route('/<https>://<server>.e-sim.org/battlesByWar.html', methods=['GET'])
def battlesByWar(https, server):
    tree = get_tree(f"{request.full_path[1:].replace(f'{https}:/', 'https://')}")
    last_page = tree.xpath("//ul[@id='pagination-digg']//li[last()-1]//@href") or ['page=1']
    last_page = int(last_page[0].split('page=')[1])
    war = tree.xpath('//*[@name="id"]//option[@selected="selected"]')[0].text.strip()

    sides = [x.replace("xflagsMedium xflagsMedium-", "").replace("-", " ") for x in
             tree.xpath('//*[@id="battlesTable"]//tr//td[1]//div//div//div/@class') if "xflagsMedium" in x]
    defender, attacker = sides[::2], sides[1::2]
    battles_id = [int(x.split("?id=")[1]) for x in tree.xpath('//tr//td[1]//div//div[2]//div[2]/a/@href')]
    battles_region = tree.xpath('//tr//td[1]//div//div[2]//div[2]/a/text()')

    score = tree.xpath('//tr[position()>1]//td[2]/text()')
    dmg = [int(x.replace(",", "").strip()) for x in tree.xpath('//tr[position()>1]//td[3]/text()')]
    battle_start = [x.strip() for x in tree.xpath('//tr[position()>1]//td[4]/text()')]
    row = {"pages": last_page, "war": war, "battles": []}
    for defender, attacker, battle_id, battle_region, score, dmg, battle_start in zip(
            defender, attacker, battles_id, battles_region, score, dmg, battle_start):
        row["battles"].append({"defender": {"name": defender, "score": int(score.strip().split(":")[0])},
                               "attacker": {"name": attacker, "score": int(score.strip().split(":")[1])},
                               "id": battle_id, "dmg": dmg, "region": battle_region, "battle start": battle_start})
    return jsonify(row)


@app.route('/<https>://<server>.e-sim.org/battles.html', methods=['GET'])
def battles(https, server):
    tree = get_tree(f"{request.full_path[1:].replace(f'{https}:/', 'https://')}")
    last_page = tree.xpath("//ul[@id='pagination-digg']//li[last()-1]//@href") or ['page=1']
    last_page = int(last_page[0].split('page=')[1])
    country = tree.xpath('//*[@id="countryId"]//option[@selected="selected"]')[0].text
    countryId = int(tree.xpath('//*[@id="countryId"]//option[@selected="selected"]/@value')[0])
    sorting = tree.xpath('//*[@id="sorting"]//option[@selected="selected"]')[0].text.replace("Sort ", "")
    filtering = tree.xpath('//*[@id="filter"]//option[@selected="selected"]')[0].text

    progress_attacker = [float(x.replace("width: ", "").split("%")[0]) for x in
                         tree.xpath("//tr//td[1]//div//div[2]//div[1]//div//div/@style")]
    progress_defender = [100 - x for x in progress_attacker]
    counter = [i.split(");\n")[0] for i in tree.xpath('//tr//td[1]//script/text()') for i in i.split("() + ")[1:]]
    counter = [f'{int(x[0]):02d}:{int(x[1]):02d}:{int(x[2]):02d}' for x in chunker(counter, 3)]
    sides = [x.replace("xflagsMedium xflagsMedium-", "").replace("-", " ") for x in
             tree.xpath('//tr//td[1]//div//div//div/@class') if "xflagsMedium" in x]
    defender, attacker = sides[::2], sides[1::2]
    battles_id = [int(x.split("?id=")[1]) for x in tree.xpath('//tr//td[1]//div//div[2]//div[2]/a/@href')]
    battles_region = tree.xpath('//tr//td[1]//div//div[2]//div[2]/a/text()')
    score = tree.xpath('//tr[position()>1]//td[2]/text()')
    dmg = [int(x.replace(",", "").strip()) for x in tree.xpath('//tr[position()>1]//td[3]/text()')]
    battle_start = [x.strip() for x in tree.xpath('//tr[position()>1]//td[4]/text()')]
    row = {"pages": last_page, "sorting": sorting, "filter": filtering, "country": country, "country id": countryId, "battles": []}
    for progress_attacker, progress_defender, counter, defender, attacker, battles_id, battles_region, score, dmg, battle_start in zip(
            progress_attacker, progress_defender, counter, defender, attacker, battles_id, battles_region, score, dmg, battle_start):
        row["battles"].append(
            {"time reminding": counter, "id": battles_id, "dmg": dmg, "region": battles_region, "started": battle_start,
             "defender": {"name": defender, "score": int(score.strip().split(":")[0]), "bar": progress_defender},
             "attacker": {"name": attacker, "score": int(score.strip().split(":")[1]), "bar": progress_attacker}})
    return jsonify(row)


@app.route('/<https>://<server>.e-sim.org/profile.html', methods=['GET'])
def profile(https, server):
    tree = get_tree(f"{request.full_path[1:].replace(f'{https}:/', 'https://')}")
    all_parameters = ["avoid", "max", "crit", "damage", "miss", "flight", "eco", "str", "hit", "less", "find"]
    slots = ['helmet', 'vision', 'personal armor', 'pants', 'shoes', 'lucky charm', 'weapon upgrade', 'offhand']
    medals = ["Congress medals", "CP", "Train", "Inviter", "Subs", "Work", "BHs", "RW", "Tester", "Tournament"]
    Friends = [x.replace("Friends", "").replace("(", "").replace(")", "") for x in
               tree.xpath("//div[@class='rank']/text()") if "Friends" in x] or [0] 
    inactive = [int(x.split()[-2]) for x in tree.xpath(f'//*[@class="profile-data red"]/text()') if "This citizen has been inactive for" in x]
    status = "0" if not inactive else str(date.today() - timedelta(days=inactive[0]))
    banned_by = [x.strip() for x in tree.xpath(f'//*[@class="profile-data red"]//div/a/text()')] or [""]
    premium = tree.xpath(f'//*[@class="premium-account"]') is True
    birthday = tree.xpath(f'//*[@class="profile-row" and span = "Birthday"]/span/text()')[0]
    debts = sum([float(x) for x in tree.xpath(f'//*[@class="profile-data red"]//li/text()')[::6]])
    assets = sum([float(x.strip()) for x in tree.xpath(f'//*[@class="profile-data" and (strong = "Assets")]//ul//li/text()') if "\n" in x])
    equipments = {}
    Index = 0
    for Q in tree.xpath('//*[@id="profileEquipmentNew"]//div/@class'):
        if "equipmentBack" in Q:
            Q = Q.replace("equipmentBack q", "")
            equipments[slots[Index]] = {"quality": int(Q)}
            Index += 1

    medals1 = {}
    for Index, medal in enumerate(medals):
        a = tree.xpath(f"//*[@id='medals']//ul//li[{Index + 1}]//div//text()")
        if a:
            medals1[medal.lower()] = int(*[x.replace("x", "") for x in a])
        elif tree.xpath(f"//*[@id='medals']//ul//li[{Index + 1}]/img/@src"):
            medals1[medal.lower()] = 1
        else:
            medals1[medal.lower()] = 0
    buffs_debuffs = [x.split("/specialItems/")[-1].split(".png")[0] for x in tree.xpath(f'//*[@class="profile-row" and (strong="Debuffs" or strong="Buffs")]//img/@src') if "//cdn.e-sim.org//img/specialItems/" in x]
    buffs = [x.split("_")[0] for x in buffs_debuffs if "positive" in x.split("_")[1:]]
    debuffs = [x.split("_")[0] for x in buffs_debuffs if "negative" in x.split("_")[1:]]
    buffs = [a.replace("vacations", "vac").replace("resistance", "sewer") for a in buffs]
    debuffs = [a.replace("vacations", "vac").replace("resistance", "sewer") for a in debuffs]
    for slot_path in tree.xpath('//*[@id="profileEquipmentNew"]//div//div//div//@title'):
        tree = fromstring(slot_path)
        try:
            Type = tree.xpath('//b/text()')[0].strip()
        except IndexError:
            continue
        parameters_string = tree.xpath('//p/text()')
        parameters = []
        full_name = []
        for parameter_string in parameters_string:
            for x in all_parameters:
                if x in parameter_string:
                    parameters.append(x)
                    full_name.append(parameter_string)
                    break
        if len(parameters) == 2:
            parameter1, parameter2 = parameters
            value1 = full_name[0].split("by ")[1].replace("%", "").strip()
            value2 = full_name[1].split("by ")[1].replace("%", "").strip()
            equipments[" ".join(Type.split()[1:]).lower()].update(
                {"first parameter": parameter1, "second parameter": parameter2,
                 "first value": float(value1), "second value": float(value2)})
    row = {"medals": medals1, "friends": int(Friends[0]), "equipments": equipments, "inactive days": inactive[0] if inactive else 0,
           "premium": premium, "birthday": birthday,
           "assets": assets, "debts": debts, "buffs": buffs, "debuffs": debuffs}
    if banned_by:
        row.update({"banned by": banned_by[0]})
    if status:
        row.update({"last login": status})
    return jsonify(row)


if __name__ == "__main__":
    app.run()

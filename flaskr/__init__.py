from neo4j import GraphDatabase
import pytz
from flask import (Flask, request, jsonify, abort)

URI = "neo4j://localhost"
AUTH = ("neo4j", "adminadmin")

def create_app():
    app = Flask(__name__)
    driver = GraphDatabase.driver(URI, auth=AUTH)
    driver.verify_connectivity()

    def runQuery(query, parameters=None):
        with driver.session() as session:
            return session.run(query, parameters=parameters).data()

    @app.route('/cities', methods=['PUT'])
    def registerCity():
        data = request.get_json()
        country, city = data.get('country'), data.get('name')

        if not country or not city or city.strip()=="" or country.strip()=="":
            return jsonify("Could not register the city: mandatory attributes are missing."), 400

        result = runQuery(
            """
            MATCH (ct:City {name: $city})
            WITH count(ct) AS exists
            WHERE exists = 0
            MERGE (c:Country {name: $country})
            MERGE (ct:City {name: $city})
            MERGE (ct)-[:LOCATED_IN]->(c)
            RETURN exists
            """,
            {"country": country, "city": city}
        )
            
        if result[0]['exists']>0:
            return jsonify("Could not register the city: it already exists."), 400
            
        return jsonify("City registered successfully."), 201
    
    @app.route('/cities', methods=['GET'])
    def getCities():
        country = request.args.get('country', default=None)
        
        if country:
            result = runQuery(
                """
                MATCH (ct:City)-[:LOCATED_IN]->(c:Country {name: $country})
                RETURN ct.name as name, c.name as country
                """,
                {"country": country}
            )
        else:
            result = runQuery(
                """
                MATCH (ct:City)-[:LOCATED_IN]->(c:Country)
                RETURN ct.name as name, c.name as country
                """
            )
            
        return jsonify(result), 200

    @app.route('/cities/<name>', methods=['GET'])
    def getCityDetails(name):
        result = runQuery(
            """
            MATCH (ct:City {name: $city})-[:LOCATED_IN]->(c:Country)
            RETURN ct.name as name, c.name as country
            """,
            {"city": name}
        )
        
        if not result:
            return jsonify("City not found."), 404
                
        return jsonify(result[0]), 200
            
    @app.route('/cities/<name>/airports', methods=['PUT'])
    def registerAirport(name):
        data = request.get_json()
        code, airportName, nrOfTerminals, address = data.get('code'), data.get('name'), data.get('numberOfTerminals'), data.get('address')

        if not all([code, airportName, nrOfTerminals, address]) or any(str(param).strip()=="" for param in [code, airportName, address]):
            return jsonify("Airport could not be created due to missing data."), 400

        validation = runQuery(
            """
            MATCH (ct:City {name: $city})
            OPTIONAL MATCH (a:Airport)
            WHERE a.code = $code OR a.name = $airportName
            RETURN count(ct) as cityExists, count(a) as airportExists
            """,
            {"city": name, "code": code, "airportName": airportName}
        )

        if validation[0]['cityExists']==0:
            return jsonify("Airport could not be created due to the city not being registered in the system."), 400

        if validation[0]['airportExists']>0:
            return jsonify("Airport could not be created due to duplicate airport name or code."), 400

        runQuery(
            """
            MATCH (ct:City {name: $city})
            MERGE (a:Airport {
                code: $code,
                name: $name,
                numberOfTerminals: $terminals,
                address: $address
            })
            MERGE (a)-[:LOCATED_IN]->(ct)
            """,
            {"city": name, "code": code, "name": airportName, "terminals": nrOfTerminals, "address": address}
        )
            
        return jsonify("Airport registered successfully."), 201

    @app.route('/cities/<name>/airports', methods=['GET'])
    def getAirportsInCity(name):
        result = runQuery(
            """
            MATCH (a:Airport)-[:LOCATED_IN]->(ct:City {name: $city})
            RETURN a.code as code, 
                ct.name as city,
                a.name as name, 
                a.numberOfTerminals as numberOfTerminals,
                a.address as address
            """,
            {"city": name}
        )

        return jsonify(result), 200

    @app.route('/airports/<code>', methods=['GET'])
    def getAirportByCode(code):
        result = runQuery(
            """
            MATCH (a:Airport {code: $code})-[:LOCATED_IN]->(ct:City)
            RETURN a.code as code, 
                ct.name as city, 
                a.name as name, 
                a.numberOfTerminals as numberOfTerminals, 
                a.address as address
            """,
            {"code": code}
        )

        if not result:
            return jsonify("Airport not found."), 404

        return jsonify(result[0]), 200

    @app.route('/flights', methods=['PUT'])
    def registerFlight():
        data = request.get_json()
        number, fromAirport, toAirport, price, flightTimeInMinutes, operator = data.get('number'), data.get('fromAirport'), data.get('toAirport'), data.get('price'), data.get('flightTimeInMinutes'), data.get('operator')

        if not all([number, fromAirport, toAirport, price, flightTimeInMinutes, operator]) or any(str(param).strip()=="" for param in [number, fromAirport, toAirport, operator]) or price<0 or flightTimeInMinutes<0:
            return jsonify("Flight could not be created due to missing or incorrect data."), 400

        result = runQuery(
            """
            MATCH (from:Airport {code: $fromAirport}), (to:Airport {code: $toAirport})
            MERGE (from)-[flight:FLIGHT {
                number: $number,
                price: $price,
                flightTimeInMinutes: $flightTimeInMinutes,
                operator: $operator
            }]->(to)
            RETURN flight
            """,
            {"number": number, "fromAirport": fromAirport, "toAirport": toAirport, "price": price, "flightTimeInMinutes": flightTimeInMinutes, "operator": operator}
        )

        if not result:
            return jsonify("Flight could not be created due to duplicate flight number."), 400

        return jsonify("Flight created."), 201
    
    @app.route('/flights/<code>', methods=['GET'])
    def findFlight(code):
        result = runQuery(
            """
            MATCH (from:Airport)-[flight:FLIGHT {number: $code}]->(to:Airport)
            MATCH (from)-[:LOCATED_IN]->(fromCity:City)
            MATCH (to)-[:LOCATED_IN]->(toCity:City)
            RETURN flight.number AS number,
                from.code AS fromAirport,
                fromCity.name AS fromCity,
                to.code AS toAirport,
                toCity.name AS toCity,
                flight.price AS price,
                flight.flightTimeInMinutes AS flightTimeInMinutes,
                flight.operator AS operator
            """,
            {"code": code}
        )

        if not result:
            return jsonify("Flight not found."), 404

        return jsonify(result[0]), 200
    
    @app.route('/search/flights/<fromCity>/<toCity>', methods=['GET'])
    def findFlightFromTo(fromCity, toCity):
        accessibleCities = runQuery(
            """
            MATCH (ct:City)
            WHERE ct.name = $fromCity OR ct.name = $toCity
            RETURN count(ct) AS accessibleCities
            """,
            {"fromCity": fromCity, "toCity": toCity}
        )

        if len(accessibleCities)==0 or accessibleCities[0]["accessibleCities"]!=2:
            return jsonify("One or both cities do not exist."), 404

        result = runQuery(
            """
            MATCH (from:Airport)-[:LOCATED_IN]->(:City {name: $fromCity}),
                (to:Airport)-[:LOCATED_IN]->(:City {name: $toCity})
            MATCH path = (from)-[:FLIGHT*]->(to)
            WHERE length(path) <= 3 
            WITH from, to, path,
                reduce(totalPrice = 0, r IN relationships(path) | totalPrice + r.price) AS totalPrice,
                reduce(totalTime = 0, r IN relationships(path) | totalTime + r.flightTimeInMinutes) AS totalTime,
                [r IN relationships(path) | r.number] AS flightNumbers
            RETURN from.code AS fromAirport,
                to.code AS toAirport,
                flightNumbers AS flights,
                totalPrice AS price,
                totalTime AS flightTimeInMinutes
            """,
            {"fromCity": fromCity, "toCity": toCity}
        )

        return jsonify(result), 200

    @app.route('/cleanup', methods=['POST'])
    def cleanup():
        runQuery(
            """
            MATCH (n) DETACH DELETE n;
            """
        )

        return jsonify("Cleanup successful."), 200

    return app


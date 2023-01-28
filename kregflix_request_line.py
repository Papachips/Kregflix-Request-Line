from flask import Flask, request, redirect
from twilio.twiml.messaging_response import MessagingResponse
from plexapi.myplex import MyPlexAccount
import sqlite3
from datetime import date
from twilio.rest import Client
import os
from arrapi import RadarrAPI
from arrapi import SonarrAPI 
from tmdbv3api import Movie
from tmdbv3api import TMDb
from tmdbv3api import TV
import traceback
import random

account = MyPlexAccount(PLEX_USER, PLEX_PW)
plex = account.resource(SERVER_NAME).connect()

conn = sqlite3.connect('kregflix.db')
cursor = conn.cursor()
sql ='''CREATE TABLE IF NOT EXISTS TV(NAME text, REQUESTER text, DATE text)'''
cursor.execute(sql)
sql ='''CREATE TABLE IF NOT EXISTS MOVIES(NAME text, REQUESTER text, DATE text)'''
cursor.execute(sql)
conn.commit()
conn.close()

urlRadarr = RADARR_LOCAL_ADDRESS
apiRadarr = RADARR_API_KEY

urlSonarr = SONARR_LOCAL_ADDRESS
apiSonarr = SONARR_API_KEY

tmdb = TMDb()
tmdb.api_key = TMDB_API_KEY

radarr = RadarrAPI(urlRadarr, apiRadarr)
sonarr = SonarrAPI(urlSonarr, apiSonarr)

tmdbMovie = Movie()
tmdbTV = TV()

app = Flask(__name__)

@app.route("/sms", methods=['GET', 'POST'])
def incoming_sms():

    rBody = request.values.get('Body', None).upper()
    requester = request.values.get('From')
    currentDate = date.today()
    resp = MessagingResponse()

#Movie request
    if rBody.startswith('MOVIE') and '-' in rBody:
        movies = plex.library.section('KregFlix Movies')
        title = rBody.replace('MOVIE', '').replace('-','').rstrip()
        search = movies.search(title)
        title = title.lower()
        if(len(search) == 0):
            conn = sqlite3.connect('kregflix.db')
            cursor = conn.cursor()
            cursor.execute("INSERT INTO MOVIES (NAME, REQUESTER, DATE) VALUES (?,?,?)", (title.title(), requester, currentDate))
            conn.commit()
            conn.close()

         
            try:
                    search = tmdbMovie.search(title)
                    if(len(search) == 0):
                        resp.message(title.title() + ' ' + 'does not exist in any database. Check the name and try again.')
                    else:
                        movieID = search[0].id
                        movie = radarr.get_movie(tmdb_id=movieID)
                        movie.add("M:\\", "HD-1080p")
                        resp.message('Movie request received for ' + title.title() + '. Consider donating to keep KregFlix running')
            except:
            	print(traceback.format_exc())
            	pass
            return str(resp)

        else:
            resp.message(title.title() + ' exists on KregFlix Movies.')
            return str(resp)
    elif ('MOVIE' in rBody):
        resp.message('Invalid format. Requesting movies should follow this format: Movie - Team America')
        return str(resp)
#TV Show request
    if rBody.startswith('SHOW') and '-' in rBody:
        shows = plex.library.section('KregFlix TV')
        title = rBody.replace('SHOW', '').replace('-','').rstrip()
        search = shows.search(title)
        title = title.lower()
        if(len(search) == 0):
            conn = sqlite3.connect('kregflix.db')
            cursor = conn.cursor()
            cursor.execute("INSERT INTO TV (NAME, REQUESTER, DATE) VALUES (?,?,?)", (title.title(), requester, currentDate))
            conn.commit()
            conn.close()

            
            try:
                    search = sonarr.search_series(title)
                    if(len(search) == 0):
                        resp.message(title.title() + ' ' + 'does not exist in any database. Check the name and try again.')
                    else:
                        tvID = search[0].tvdbId
                        tv = sonarr.get_series(tvdb_id=tvID)
                        tv.add("T:\\", "HD-1080p", "English")
                        resp.message('TV show request received for ' + title.title() + '. Consider donating to keep KreFlix running')
            except:
            	print(traceback.format_exc())
            	pass
            return str(resp)
        else:
            resp.message(title.title() + ' exists on KregFlix TV up to season ' + str(search[0].childCount) +  '.')
            return str(resp)
    elif ('SHOW' in rBody):
        resp.message('Invalid format. Requesting TV shows should follow this format: Show - The Office')
        return str(resp)

#Add friend
    if rBody.startswith('INVITE') and '@' in rBody:
        email = rBody.replace('INVITE - ','').rstrip()
        plex.myPlexAccount().inviteFriend(email, plex, sections=['Kregflix Movies', 'Kregflix TV'])
        resp.message('An invite has been sent to ' + email + '.')
        return str(resp)

#Server status
    if rBody.startswith('STATUS'):
        kregFlixStatus = os.system('ping -c 3 -w 3000 LOCAL_PLEX_SERVER_ADDRESS')
        if kregFlixStatus == 0:
            resp.message('KregFlix server is up.')
            return str(resp)
        else:
            resp.message('Kregflix server is down.')
            return str(resp)

if __name__ == "__main__":
    app.run(port=5000)

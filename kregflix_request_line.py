from flask import Flask, request, redirect
from twilio.twiml.messaging_response import MessagingResponse
from plexapi.myplex import MyPlexAccount
import sqlite3
from datetime import date
from twilio.rest import Client
import os
from arrapi import RadarrAPI,SonarrAPI,exceptions
from tmdbv3api import TMDb,Movie,TV
import traceback

#plex connection
account = MyPlexAccount(PLEX_USER, PLEX_PW)
plex = account.resource(PLEX_SERVER).connect()
print('connected to plex')

#db setup in case of new env setup
conn = sqlite3.connect(DB_FILE_PATH)
cursor = conn.cursor()
sql ='''CREATE TABLE IF NOT EXISTS TV(NAME text, REQUESTER text, DATE text)'''
cursor.execute(sql)
sql ='''CREATE TABLE IF NOT EXISTS MOVIES(NAME text, REQUESTER text, DATE text)'''
cursor.execute(sql)
conn.commit()
conn.close()

#radarr login
urlRadarr = RADARR_LOCAL_URL
apiRadarr = RADARR_API_KEY
radarr = RadarrAPI(urlRadarr, apiRadarr)
print('logged into radarr')

#sonarr login
urlSonarr = SONARR_LOCAL_URL
apiSonarr = SONARR_API_KEY
sonarr = SonarrAPI(urlSonarr, apiSonarr)
print('logged into sonarr')

#TMDB movie and tv instantiations
tmdb = TMDb()
tmdb.api_key = TMDB_APY_KEY
tmdbMovie = Movie()
tmdbTV = TV()
print('logged into tmdb')

app = Flask(__name__)

@app.route("/sms", methods=['GET', 'POST'])
#requestText = body of text message containing request
#requester = phone number of person requesting media
#response = automated response text message body
def incoming_sms():
    print('yep')
    requestText = request.values.get('Body', None).upper() #upper to normalize input to check for prefix
    requester = request.values.get('From') #for logging purposes
    currentDate = date.today() #for logging purposes
    response = MessagingResponse()

#Movie request - requests to be prefixed with 'movie - '
    if requestText.startswith('MOVIE') and '-' in requestText:
        #gets current movie library object
        movies = plex.library.section(MOVIE_LIBRARY_NAME)
        #remove movie prefix and any leading/trailing spaces. change to title case from here on
        title = requestText.replace('MOVIE -', '').replace('-','').rstrip().lstrip().title()
        #search current plex library object for request to see if it exists
        search = movies.search(title)

        #if no matches in plex library we want to continue and log the request as a backup
        if(len(search) == 0):
            conn = sqlite3.connect(DB_FILE_PATH)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO MOVIES (NAME, REQUESTER, DATE) VALUES (?,?,?)", (title, requester, currentDate))
            conn.commit()
            conn.close()
            try:
                    #search movie on TMDb to see if it even exists
                    search = tmdbMovie.search(title)
                    #if it's not found, return text message indicating to user
                    if(len(search) == 0):
                        response.message(title + ' ' + 'does not exist in any database. Check the name and try again.')
                        return str(response)
                    #if it does exist, attempt to add to radarr's queue
                    else:
                        #most likely the first result in any search. very rare for this not to be the case
                        movieID = search[0].id
                        #radarr uses TMDb ids to add movies to the queue 
                        movie = radarr.get_movie(tmdb_id=movieID)
                        #drive location and the media quality tag to add
                        movie.add(DRIVE_PATH, "HD-1080p")
                        #return text message indicating the movie was added to the queue successfully to the user
                        response.message('Movie request received for ' + title + '. Consider donating to keep KregFlix running: paypal.me/CraigRondinelli')
                        return str(response)
            except exceptions.Exists as e:
                #we want to specifically catch the exception that the movie is already in the queue and return a text message saying as much to the user
                response.message(title.title() + ' is already in the system to download when available.')
                return str(response)
            except:
                #any other errors we will just print in the cmd window and pass. no need to terminate the script in case some weird, one off error crops up
                print(traceback.format_exc())
                pass
        #if there is a match in the plex library, return a text message letting the user know
        else:
            response.message(title.title() + ' exists on MOVIE_LIBRARY_NAME.')
            return str(response)

#TV Show request - requests to be prefixed with 'show -'
#this code is identical in functionality to the movie requests
#it just uses sonarr instead of radarr
    if requestText.startswith('SHOW') and '-' in requestText:
        shows = plex.library.section(TV_LIBRARY_NAME)
        title = requestText.replace('SHOW', '').replace('-','').rstrip().lstrip().title()
        search = shows.search(title)
        if(len(search) == 0):
            conn = sqlite3.connect(DB_FILE_PATH)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO TV (NAME, REQUESTER, DATE) VALUES (?,?,?)", (title, requester, currentDate))
            conn.commit()
            conn.close()
            try:
                    search = sonarr.search_series(title)
                    if(len(search) == 0):
                        response.message(title + ' ' + 'does not exist in any database. Check the name and try again.')
                        return str(response)

                    else:
                        tvID = search[0].tvdbId
                        tv = sonarr.get_series(tvdb_id=tvID)
                        tv.add(DRIVE_PATH, "HD-1080p", "English")
                        response.message('TV show request received for ' + title + '. Consider donating to keep KregFlix running: paypal.me/CraigRondinelli')
                        return str(response)
            except exceptions.Exists as e:
                response.message(title + ' is already in the system to download when available.')
                return str(response)
            except:
                print(traceback.format_exc())
                pass
        else:
            response.message(title + ' exists on TV_LIBRARY_NAME up to season ' + str(search[0].childCount) +  '.')
            return str(response)

#Add friend to plex server
    #look for invite and @ symbol for an email
    #this also eliminates any logic issues if a show or movie has the word 'invite' in it
    #this is 99.9% used by me only to invite people
    if requestText.startswith('INVITE') and '@' in requestText:
        try:
            #remove 'invite - ' from text message body
            email = requestText.replace('INVITE - ','').rstrip()
            #invite friends to have access to movies and shows libraries by default
            plex.myPlexAccount().inviteFriend(email, plex, sections=[LIBRARY_NAMES_TO_GIVE_ACCESS_TO])
            #return text message to user letting them know
            response.message('An invite has been sent to ' + email + '.')
            return str(response)
        #rare occurence if plex server is down when someone tries to invite themselves
        except:
            response.message('An error has occurred. You will be added manually - no need to try again')
            return str(response)

#Server status - must be prefixed with 'status'
#easy way to see if server is online
#99.9% only used by me
    if requestText.startswith('STATUS'):
        #-c 3 parameter sends only 3 packets
        #-w 30 parameter will stop attempting after 30 seconds
        kregFlixStatus = os.system('ping -c 3 -w 30 SERVER_IP_ADDRESS')
        #0 is good
        if kregFlixStatus == 0:
            kregFlixService = os.system('nc -vz SERVER_IP_ADDRESS 32400')
            if(kregFlixService == 0 or kregFlixService == 32512):
                response.message('KregFlix server is up.')
                return str(response)
            else:
                response.message('KregFlix server is up, but the service has encountered an error.')
                return str(response)
        else:
            response.message('Kregflix server is down.')
            return str(response)

if __name__ == "__main__":
    app.run(port=5000)

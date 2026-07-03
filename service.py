import requests, os, sys, time, json
import GoogleRecaptchaBypass
from RecaptchaSolver import RecaptchaSolver





class API_ttc:
    def __init__(self, access_token):
        self.access_token = access_token
        self.session = requests.Session()


    def info_user(self):
        

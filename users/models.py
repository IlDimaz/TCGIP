from django.contrib.auth.models import AbstractUser
from django.db import models

#settings per il form
class User(AbstractUser):
    profile_image = models.ImageField(upload_to="users/profiles/", null=True, blank=True)
    city = models.CharField( max_length=100,blank=True)
    province = models.CharField(max_length=100,blank=True)
    country = models.CharField(max_length=100,blank=True,default='Italia')
    allow_location = models.BooleanField(default=False,help_text='Se spuntato, gli altri utenti potranno vedere la tua posizione')
    collection_public = models.BooleanField(default=False, help_text='Se spuntato, chiunque potrà vedere la tua collezione dal tuo profilo pubblico')

    def __str__(self):
        return self.username

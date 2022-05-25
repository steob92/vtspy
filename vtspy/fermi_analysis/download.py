import numpy as np
import os, sys
import urllib
import time
import yaml

from astropy.io import fits
from GtBurst import html2text

import re

from .config import config

class DownloadFermiData:
    
    def __init__(self, file = "config_fermi.yaml", verbose=False, **kwargs):
        
        self.file = file
        self.config = config.getConfig(self.file)
        
        self.verbose = verbose

        if self.config['selection']['target'] == None:
            self.target = "source"
        else:
            self.target = self.config['selection']['target']

        self.coordsys = self.config['binning']['coordsys']
        if self.coordsys == "GAL":
            self.coord = "Galactic"
            self.loc = [self.config['selection']['glon'], self.config['selection']['glat']]
        elif self.coordsys == "CEL":
            self.coord = "J2000"
            self.loc = [self.config['selection']['ra'], self.config['selection']['dec']]
        
        if self.loc[0] == None or self.loc[1] == None:
            print("[Error] Coordinates (e.g., RA & DEC) is not specified.")
            return
        
        self.tmin = self.config['selection']['tmin']
        self.tmax = self.config['selection']['tmax']    
        if self.tmin == None or self.tmax == None:
            print("[Error] Time range is not specfied.")
            return

        self.emin = self.config['selection']['emin']
        self.emax = self.config['selection']['emax']

        success = self.__query__()

        if success:
            self.__download__()

    def __query__(self, verbose=True):

        self.verbose=max(verbose, self.verbose)
        
        url                         = "https://fermi.gsfc.nasa.gov/cgi-bin/ssc/LAT/LATDataQuery.cgi"
        parameters                  = {}
        parameters['coordfield']    = "%s,%s" %(self.loc[0], self.loc[1])
        parameters['coordsystem']   = "%s" %(self.coord)
        parameters['shapefield']    = "%s" %(15)
        parameters['timefield']     = "%s,%s" %(self.tmin,self.tmax)
        parameters['timetype']      = "%s" %("MET")
        parameters['energyfield']   = "%s,%s" %(self.emin,self.emax)
        parameters['photonOrExtendedOrNone'] = "Extended"
        parameters['destination']   = 'query'
        parameters['spacecraft']    = 'checked'

        if self.verbose:
            print("[Log] Query parameters:")
            for k,v in parameters.items():
                print("%30s = %s" %(k,v))

        postData                    = urllib.parse.urlencode(parameters).encode("utf-8")
        temporaryFileName           = "__temp_query_result.html"
        try:
            os.remove(temporaryFileName)
        except:
            pass
        pass

        urllib.request.urlcleanup()

        urllib.request.urlretrieve(url, temporaryFileName, lambda x,y,z:0, postData)

        with open(temporaryFileName) as htmlFile:
            lines = []
            for line in htmlFile:
                lines.append(line.encode('utf-8'))

            html = "".join(str(lines)).strip()
        
        if self.verbose == 2: print("\nAnswer from the LAT data server:\n")
        
        text = html2text.html2text(html.strip()).split("\n")
        text = list(filter(lambda x:x.find("[") < 0 and  x.find("]") < 0 and x.find("#") < 0 and x.find("* ") < 0 and
                        x.find("+") < 0 and x.find("Skip navigation")<0,text))
        text = list(filter(lambda x:len(x.replace(" ",""))>1,text))
        text = [t for t in text if t[0] != '\\']

        
        for t in text:
            if "occurs after data end MET" in t:
                maxTime = re.findall("occurs after data end MET \(([0-9]+)\)", t)[0]
                print("[Error] The current Fermi Data Server does not have data upto the entered 'tmax'.")
                print("[Error] 'tmax' value in the config file is changed to the maximum value.")
                print("[Error] config['selection']['tmax'] = ", maxTime)
                print("[Error] Please try again.")
                self.config['selection']['tmax'] = float(maxTime)
                config.updateConfig(self.config, self.file)
                return False


        text[-3] = text[-3]+" "+text[-2]
        text.remove(text[-2])
        text[-2] = text[-2]+text[-1]
        text.remove(text[-1])

        if self.verbose == 2: 
            for t in text: print(t)

        os.remove(temporaryFileName)
        estimatedTimeForTheQuery = re.findall("The estimated time for your query to complete is ([0-9]+) seconds",text[11])[0]
        self.httpAddress = text[11].split()[-1][1:-2]

        startTime = time.time()
        timeout = 2.*max(5.0,float(estimatedTimeForTheQuery))
        regexpr = re.compile("wget (.*.fits)")

        links = None
        fakeName = "__temp__query__result.html"

        overTime = False
        while(time.time() <= startTime+timeout):
            remainedTime = int(int(estimatedTimeForTheQuery) - (time.time()-startTime))
            
            if self.verbose:
                if remainedTime>0:
                    print("[Log] About "+str(remainedTime)+" seconds remain until the Fermi data is ready.   ", end="\r")
                elif not(overTime):
                    overTime=True
                    print("[Log] The Fermi data is still not ready. Wait for another " + str(int(estimatedTimeForTheQuery)) + " seconds.")
                    print("[Log] Check the link, ", self.httpAddress)

            try:
                (filename, header) = urllib.request.urlretrieve(self.httpAddress,fakeName)
            except:
                urllib.request.urlcleanup()
                continue
            
            with open(fakeName) as f:
                html = " ".join(f.readlines())
                try:
                    status = re.findall("The state of your query is ([0-9]+)",html)[0]
                except:
                    status = '0'
                    pass

                if(status=='2'):
                    links = regexpr.findall(html)
                    if len(links) >= 2:
                        break
                
            os.remove(fakeName)
            urllib.request.urlcleanup()
        
        if not(os.path.isdir("fermi")):
            os.system("mkdir fermi")

        try:
            os.remove(fakeName)
        except:
            print("[Error] The files (SC and EV files) are not ready to be downloaded. Check the link and then use 'DownloadFermiData.manualDownload()' when the data is ready.")
            return
        
        np.save("./fermi/fermi_dwn_link", links)

        return True

    def __download__(self):

        links = np.load("./fermi/fermi_dwn_link.npy")

        for lk in links:
            if self.verbose: print("[Log] Downloading... ", lk)
            fileName = lk[-9:-5]

            if "SC" in lk:
                self.config['data']['scfile'] = "./fermi/{}.fits".format( fileName)
            else:
                self.config['data']['evfile'] = "./fermi/EV00.lst"
                with open("./fermi/EV00.lst", "a") as f:
                    f.write(fileName+".fits\n")

            urllib.request.urlretrieve(lk, "./fermi/{}.fits".format(lk[-9:-5]))

        if self.verbose: print("[Log] Downloading the Fermi-LAT data has been completed.")
        os.system("rm ./fermi/fermi_dwn_link.npy")
        config.updateConfig(self.config, self.file)

    def manualDownload(self, httpAddress=None):
        
        if httpAddress!=None:
            self.httpAddress = httpAddress

        links = None
        fakeName = "__temp__query__result.html"
        regexpr = re.compile("wget (.*.fits)")

        (filename, header) = urllib.request.urlretrieve(self.httpAddress,fakeName)
        
        with open(fakeName) as f:
            html = " ".join(f.readlines())
            links = regexpr.findall(html)
        
        os.remove(fakeName)
        urllib.request.urlcleanup()

        if not(os.path.isdir("fermi")):
            os.system("mkdir fermi")
        
        np.save("./fermi/fermi_dwn_link", links)

        self.__download__()



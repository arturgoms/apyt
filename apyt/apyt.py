#!/usr/bin/python2
# encoding=utf8  

import os
import requests
import sys
import argparse
import pymongo
import json
import tempfile
import bz2
import gzip
import pprint
import validators
import hashlib
import urlparse
import shutil

class Apyt():

    ERROR = -1
    WARNING = 1
    SUCCESS = 0
    MESSAGE = None

    def __init__(self):

        self.__workdir = os.path.dirname(os.path.abspath(__file__))
        self.__sourcedir = os.path.join(self.__workdir,"lists")
        self.__sourcefile = os.path.join(self.__sourcedir,"sources.json")
        self.__tmpdir = os.path.join(self.__workdir,"tmp")
        self.__repodir = os.path.join(self.__workdir,"repos")
        
        if os.path.isdir(self.__sourcedir) is False:
            os.makedirs(self.__sourcedir)  

        if os.path.isdir(self.__tmpdir) is False:
            os.makedirs(self.__tmpdir)    

        if os.path.isdir(self.__repodir) is False:
            os.makedirs(self.__repodir)

        if os.path.isfile(self.__sourcefile) is False:
            with open(self.__sourcefile, "wb") as source_file:
                json.dump([], source_file)


    def add_repo(self, repo_url, release_path="./"):
        """
            Add repo to list
        """
        err_validate = self.__validate_repo(repo_url)
        if err_validate["type"] is self.SUCCESS:
            err_release, tmp_path_release = self.__download_release(urlparse.urljoin(repo_url, release_path))
            err_package, tmp_path_package = self.__download_package(urlparse.urljoin(repo_url, ""))
            if err_release["type"] is not self.ERROR and err_package["type"] is self.SUCCESS:
                path_release = None
                if tmp_path_release is not None:
                    path_release = os.path.join(self.__repodir, "{}_{}_{}.json".format(urlparse.urlparse(repo_url).netloc, 
                        "Release" ,self.__md5_file(tmp_path_release)))
                    os.rename(tmp_path_release, path_release)
                else:
                    self.status(err_release)

                path_package = os.path.join(self.__repodir, "{}_{}_{}.json".format(urlparse.urlparse(repo_url).netloc, 
                    "Packages" ,self.__md5_file(tmp_path_package)))
                os.rename(tmp_path_package, path_package)

                repo_data = {
                    "repo": repo_url, 
                    "release": path_release, 
                    "packages": path_package
                    }
                with open(self.__sourcefile) as source_file:
                    data = json.load(source_file)
                data.append(repo_data)
                with open(self.__sourcefile, 'w') as source_file:
                    json.dump(data, source_file)
                
                self.status({"type":self.SUCCESS, "msg":"repo {} added".format(repo_url)})
                self.__clean_tmp()
                exit(self.SUCCESS)
            else:
                self.status(err_release)
                self.status(err_package)
                self.__clean_tmp()
                exit(self.ERROR)
        else:
            self.status(err_validate)
            exit(err_validate["type"])


        pass

    def rm_repo(self, repo_url):
        """
            Remove repo from list
        """
        return_err = {"type": self.ERROR, "msg": "DEFAULT ERROR MSG"}
        data = None
        with open(self.__sourcefile) as source_file:
            data = json.load(source_file)
            repo_rm = None
            for repo in data:
                if repo["repo"] == repo_url:
                    repo_rm = data.index(repo)
                    if repo["release"] is not None:
                        os.remove(repo["release"])
                    if repo["packages"] is not None:
                        os.remove(repo["packages"])
                    break
            if repo_rm is not None:
                del data[repo_rm]
                return_err = {"type":self.SUCCESS, "msg":"Repo removed from sources json"}
                
            else:
                return_err = {"type":self.ERROR, "msg":"Repo not found"}
                
        if return_err["type"] is not self.ERROR:
            with open(self.__sourcefile, 'w') as source_file:
                json.dump(data, source_file)
                return_err = {"type":self.SUCCESS, "msg":"repo {} removed".format(repo_url)} 
    
        self.status(return_err)
        self.__clean_tmp()
        exit(return_err["type"])

    def list_repos(self):
        """
            List all repos
        """
        return_err = {"type": self.ERROR, "msg": "DEFAULT ERROR MSG"}
        data = None
        with open(self.__sourcefile) as source_file:
            data = json.load(source_file)
            if len(data) >= 1:
                for repo in data:
                    print(repo["repo"])
                return_err = {"type":self.SUCCESS, "msg":"Repos listed"} 
            else:
                return_err = {"type":self.ERROR, "msg":"Empty source file"}

        self.status(return_err)
        self.__clean_tmp()
        exit(return_err["type"])

    def search(self, packages_name):
        """
            Search for packages in all repos 
        """
        return_err = {"type": self.ERROR, "msg": "DEFAULT ERROR MSG"}
        data = None
        response = []
        with open(self.__sourcefile) as source_file:
            data = json.load(source_file)
            if len(data) >= 1:
                for repo in data:        
                    with open(repo["packages"]) as packages_file:
                        packages = json.load(packages_file)
                        for package in packages:
                            try:
                                if ("Name" in package and package["Name"] == packages_name) or (package["Package"] == packages_name):
                                    resp_found = {}
                                    resp_found["Repo"] = repo["repo"]
                                    resp_found["Package"] = package["Package"]
                                    resp_found["Version"] = package["Version"]
                                    resp_found["Description"] = package["Description"]
                                    response.append(resp_found)
                                    return_err = {"type": self.SUCCESS, "msg": "Packages found."}
                                    
                            except Exception as err:
                                return_err = {"type": self.ERROR, "msg": "Package not found."}

        if return_err["type"] == self.ERROR:
            return_err = {"type": self.ERROR, "msg": "Package not found"}

        pprint.pprint(response)
        self.status(return_err)
        self.__clean_tmp()
        exit(return_err["type"])

    
    def update(self, force=False):
        """
            Update repos by downloading the Packages file again if needed
        """
        return_err = {"type": self.ERROR, "msg": "DEFAULT ERROR MSG"}
        data = None
        response = []
        try:
            with open(self.__sourcefile) as source_file:
                data = json.load(source_file)
            if len(data) >= 1:
                for repo in data:
                    rep, name, md5 = repo["packages"].split("_")
                    md5 = md5.split(".")[0]
                    err_package, tmp_path_package = self.__download_package(urlparse.urljoin(repo["repo"], ""))
                    tmp_md5 = self.__md5_file(tmp_path_package)
                    if md5 == tmp_md5:
                        return_err = {"type": self.SUCCESS, "msg": "Repo {} Already updated.".format(repo["repo"])}
                        self.status(return_err)
                    else:
                        os.remove(repo["packages"])
                        path_package = os.path.join(self.__repodir, "{}_{}_{}.json".format(urlparse.urlparse(repo["repo"]).netloc, 
                            "Packages" ,tmp_md5))
                        os.rename(tmp_path_package, path_package)
                        return_err = {"type": self.SUCCESS, "msg": "Repo {} updated - last_md5: {} new_ma5: {} .".format(repo["repo"],md5, tmp_md5 )}
                        self.status(return_err)
                        data[data.index(repo)]["packages"] = path_package
                        with open(self.__sourcefile, 'w') as source_file:
                            json.dump(data, source_file)

        except Exception as err:
            print(err)
            return_err = {"type": self.ERROR, "msg": "Error updating repos."}
            self.status(return_err)

        self.__clean_tmp()
        exit(return_err["type"])

    def package(self, packages_name=None, repo=None, version=None):
        """
            Show info from package
        """
        pass

    def list_packages(self, repo_name=None):
        """
            List packages of repo, if repo is empty list all packages
        """
        return_err = {"type": self.ERROR, "msg": "DEFAULT MSG ERROR"}
        data = None
        response = []
        try:
            with open(self.__sourcefile) as source_file:
                data = json.load(source_file)
                
                if len(data) >= 1:
                    for repo in data:
                        if repo["repo"] == repo_name:   
                            with open(repo["packages"]) as packages_file:
                                packages = json.load(packages_file)
                                response = packages
                                return_err = {"type": self.SUCCESS, "msg": "All packages from {} retrived".format(repo_name)}
                                break
                        elif repo_name == "all":
                            with open(repo["packages"]) as packages_file:
                                packages = json.load(packages_file)
                                response.append(packages)
                                return_err = {"type": self.SUCCESS, "msg": "All packages retrived"}
        except Exception as err:
            return_err = {"type": self.ERROR, "msg": "Packages from that repository not found"}

        pprint.pprint(response)
        self.status(return_err)
        self.__clean_tmp()
        exit(return_err["type"])


    def __validate_repo(self, repo):
        """
            Check if the repo not exists. Release file is not necessary
        """
        # Check if repo already exists
        return_err = {"type": self.WARNING, "msg": "DEFAULT ERROR MSG"}
        new_repo = True
        with open(self.__sourcefile) as source_file:
            data = json.load(source_file)
            for repos in list(data):
                if repos["repo"] == repo:
                    new_repo = False
                    break
        if new_repo:
            return_err["type"] = self.SUCCESS
            return_err["msg"] = "It's a new repo"
        else:
            return_err["msg"] = "Repo {} already exists in database, run update maybe?".format(repo)

        return return_err

    def __download_release(self, repo):
        """
            Trying to retrive release file
        """
        return_err = {"type": self.ERROR, "msg": "DEFAULT ERROR MSG"}
        path_release = None
        try:
            md5 = hashlib.md5()
            url = urlparse.urljoin(repo, "Release")
            file = requests.get(url)
            if file.status_code == 200:
                data = file.content
                return_err["msg"] = "File downloaded."
                releases = data.split("\n\n")
                for release_info in releases:
                    release = {}
                    release_values = release_info.split("\n")
                    for release_dict in release_values:
                        if len(release_dict) > 1:
                            try:
                                id, value = release_dict.split(":", 1)
                                release[id] = value.strip()
                            except Exception as err:
                                return_err["type"] = self.ERROR
                                return_err["msg"] = "{}".format(err)
                    if release != {}:
                        with open(os.path.join(self.__tmpdir, "{}_{}".format(urlparse.urlparse(repo).netloc, "Release")), "wb") as ReleaseFile:
                            json.dump(release, ReleaseFile)
                            path_release = os.path.join(self.__tmpdir, "{}_{}".format(urlparse.urlparse(repo).netloc, "Release"))
                            return_err["type"] = self.SUCCESS
                            return_err["msg"] = "Release file retrived."

            else:
                return_err["type"] = self.WARNING
                return_err["msg"] = "Release file not found."
                path_release = None

        except Exception as err:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            return_err["type"] = self.ERROR
            return_err["msg"] = "{} {} {} {}".format(exc_type, fname, exc_tb.tb_lineno, err)
        
        return return_err, path_release

    def __download_package(self, repo):
        """
            Trying to retrive release file
        """
        return_err = {"type": self.ERROR, "msg": "DEFAULT ERROR MSG"}
        path_packages = None
        packages_list = ["Packages.bz2", "Packages.gz", "dists/stable/main/binary-iphoneos-arm/Packages.gz",  "dists/stable/main/binary-iphoneos-arm/Packages.bz2", "Packages", ]

        file = None
        url = None
        data = None
        repo_packages = []
        
        try:
            for package_name in packages_list:
                path = urlparse.urlsplit(repo).path + package_name
                url = urlparse.urljoin(repo, path)
                file = requests.get(url)
                if file.status_code == 200:
                    packages_file = tempfile.TemporaryFile(mode = 'w+')
                    packages_file.write(file.content)
                    packages_file.seek(0)
                    extension = package_name.split(".")
                    if len(extension) > 1:
                        try:
                            if extension[1] == "bz2":
                                bz2_file = packages_file.read()
                                obj=bz2.BZ2Decompressor()
                                data = obj.decompress(bz2_file)
                            elif extension[1] == "gz":
                                gzf = gzip.GzipFile(mode='rb', fileobj=packages_file)
                                data = gzf.read()
                            else:
                                data = None
                                return_err["msg"] = "File type not supported"
                        except:
                            return_err["msg"] = "File type not supported"

                    else:   
                        data = file.text
                    break
            if data is not None:
                packages = data.split("\n\n")
                for package_info in packages:
                    package = {}
                    package_values = package_info.split("\n")
                    for package_dict in package_values:
                        if len(package_dict) > 1:
                            try:
                                id, value = package_dict.split(":", 1)
                                package[id] = value.strip().decode('utf-8')
                            except KeyError as err:
                                print(err)
                            except Exception as err:
                                if "Description" in package:
                                    package["Description"] = package["Description"] + package_dict.decode('latin-1')
                    if package != {}:
                        repo_packages.append(package)
                
                with open(os.path.join(self.__tmpdir, "{}_{}".format(urlparse.urlparse(repo).netloc, "Packages")), "wb") as PackagesFile:
                    json.dump(repo_packages, PackagesFile)
                    path_packages = os.path.join(self.__tmpdir, "{}_{}".format(urlparse.urlparse(repo).netloc, "Packages"))
                    return_err["type"] = self.SUCCESS
                    return_err["msg"] = "Packages file retrived"

            else:
                return_err["msg"] = "Empty package file."
            

        except Exception as err:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            return_err["type"] = self.ERROR
            return_err["msg"] = "{} {} {} {}".format(exc_type, fname, exc_tb.tb_lineno, err)

        return return_err, path_packages

    def __md5_file(self, filePath):
        with open(filePath, 'rb') as fh:
            m = hashlib.md5()
            while True:
                data = fh.read(8192)
                if not data:
                    break
                m.update(data)
            return m.hexdigest()
    
    def __clean_tmp(self):
        shutil.rmtree(self.__tmpdir)

    def status(self, msg_status):
        if msg_status["type"] == self.ERROR:
            print("ERROR: {}".format(msg_status["msg"]))
        elif msg_status["type"] == self.WARNING:
            print("WARNING: {}".format(msg_status["msg"]))
        elif msg_status["type"] == self.SUCCESS:
            print("SUCCESS: {}".format(msg_status["msg"]))



if __name__ == "__main__":

    parser = argparse.ArgumentParser()
   
    parser.add_argument('-r',  '--addrepo', help="Add new repo")
    parser.add_argument('-d',  '--rmrepo', help="Remove repo")
    parser.add_argument('-s',  '--search', help="Search for package in all repos")
    parser.add_argument('-lr', '--listrepo', help="List all repos added",default=False, action='store_true')
    parser.add_argument('-lp', '--listpkg', help="List packages from repo, or all packages if no value" , nargs='?', const="all", type=str)
    parser.add_argument('-u',  '--update', help="Update repos",default=False, action='store_true')

    args = parser.parse_args()
    apyt = Apyt()

    if args.addrepo is not None:
        apyt.add_repo(args.addrepo)
    
    if args.rmrepo is not None:
        apyt.rm_repo(args.rmrepo)

    if args.listrepo is not False:
        apyt.list_repos()

    if args.search is not None:
        apyt.search(args.search)

    if args.listpkg is not None:
        apyt.list_packages(args.listpkg)

    if args.update is not False:
        apyt.update()
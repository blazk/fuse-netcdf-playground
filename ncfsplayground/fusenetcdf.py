#!/usr/bin/env python

"""
Exploring ideas for ESoWC project:
https://github.com/dvalters/fuse-netcdf
"""

import os
import sys
import netCDF4 as ncpy
import time
import numpy
import inspect
import argparse
import logging as log
from fuse import FUSE, FuseOSError, Operations
from errno import EACCES, ENOENT


class InternalError(Exception):
    pass


#
# Data Representation plugins
#


class VardataAsBinaryFiles(object):

    def __init__(self):
        pass

    def size(self, variable):
        """ Return size (in bytes) of data representation """
        return len(self(variable))

    def __call__(self, variable):
        """ Return Variable's data representation """
        data = variable[:].tobytes()
        return data


class VardataAsFlatTextFiles(object):

    def __init__(self, fmt='%f'):
        self._fmt = fmt

    def size(self, variable):
        """ Return size (in bytes) of data representation """
        return len(self(variable))

    def __call__(self, variable):
        """ Return Variable's data representation """
        return ''.join(numpy.char.mod(
            '{}\n'.format(self._fmt), variable[:].flatten()))


class AttributesAsTextFiles(object):

    def __init__(self):
        pass

    def size(self, attr):
        return len(self(attr))

    def __call__(self, attr):
        """ Return array of bytes representing attribute's value """
        return str(attr) + '\n'



#
# NetCDF filesystem implementation
#

class NCFS:
    """
    Main object for netCDF-filesytem operations
    """
    def __init__(self, dataset, vardata_repr, attr_repr):
        self.dataset = dataset
        # plugin for generating Variable's data representations
        self.vardata_repr = vardata_repr
        # plugin for generation Atributes representations
        self.attr_repr = attr_repr
        # a table of open files, indexed by a
        self.mount_time = time.time()

    def is_var_dir(self, path):
        """ Test if path is a valid Variable directory path """
        return path.lstrip('/') in self.dataset.variables

    def is_var_data(self, path):
        """ Test if path is a vaild path to Variable data representation
            TODO: data representation could be a file or a directory.
        """
        return 'DATA_REPR' in path

    def is_var_dimensions(self, path):
        """ Test if path is a valid path for Variable's 'dimensions' file """
        return 'dimensions' in path

    def is_var_attribute(self, path):
        """ Test if path is a valid path for Variable's Attribute """
        if '.Trash' in path:
            return False
        return not (
                self.is_var_dir(path) or
                self.is_var_data(path) or
                self.is_var_dimensions(path))

    def exists(self, path):
        """ Test if path already exists """
        # TODO: implement this
        return True


    def is_dir(self, path):
        """ Test if path corresponds to a directory-like object """
        return self.is_var_dir(path)

    def is_blacklisted(self, path):
        """ Test if a special file/directory """
        return '.Trash' in path

    def is_file(self, path):
        """ Test if path corresponds to a file-like object """
        return not self.is_dir(path)

    def get_varname(self, path):
        """ Return NetCDF variable name, given its path """
        return path.lstrip('/').split('/', 1)[0]

    def get_attrname(self, path):
        """ Return attribute name, given its path """
        return path.split('/')[-1]

    def get_variable(self, path):
        """ Return NetCDF Variable object, given its path """
        varname = self.get_varname(path)
        return self.dataset.variables[varname]

    def get_attribute(self, path):
        """ Return NetCDF Attribute object, given its path """
        varname = self.get_varname(path)
        attrname = self.get_attrname(path)
        return self.dataset.variables[varname].getncattr(attrname)

    def getncAttrs(self, path):
        """ Return name of NetCDF attributes, given variable's path """
        varname = self.get_varname(path)
        attrs = self.dataset.variables[varname].ncattrs()
        return [attr for attr in attrs]


    @classmethod
    def makeIntoDir(cls, statdict):
        """Update the statdict if the item in the VFS should be
        presented as a directory
        """
        log_call()
        statdict["st_mode"] = statdict["st_mode"] ^ 0o100000 | 0o040000
        for i in [[0o400, 0o100], [0o40, 0o10], [0o4, 0o1]]:
            if (statdict["st_mode"] & i[0]) != 0:
                statdict["st_mode"] = statdict["st_mode"] | i[1]
        return statdict


    def getattr(self, path):
        """The getattr callback is in charge of reading the metadata of a
            given path, this callback is always called before any operation
            made on the filesystem.

        We are telling FUSE that the current entry is a file
        or a directory using the stat struct.
        In general, if the entry is a directory, st_mode have to be set
        to S_IFDIR and st_nlink to 2, while if it’s a file, st_mode have
        to be set to S_IFREG (that stands for regular file) and st_nlink
        to 1. Files also require that the st_size (the full file size) is
        specified.
        """
        log_call()
        # default attributes, correspond to a regular file
        statdict = dict(
                st_atime = self.mount_time,
                st_ctime = self.mount_time,
                st_gid = os.getgid(),
                st_mode = 33188,  # file
                st_mtime = self.mount_time,
                st_nlink = 1,
                st_size = 4096,
                st_uid = os.getuid())
        path = path.lstrip('/')
        if path == "":
            statdict = self.makeIntoDir(statdict)
        elif self.is_blacklisted(path):
            return statdict
        elif not self.exists(path):
            raise FuseOSError(ENOENT)
        elif self.is_var_dir(path):
            statdict = self.makeIntoDir(statdict)
            statdict["st_size"] = 4096
        elif self.is_var_attribute(path):
            attr = self.get_attribute(path)
            statdict["st_size"] = self.attr_repr.size(attr)
        elif self.is_var_data(path):
            var = self.get_variable(path)
            statdict["st_size"] = self.vardata_repr.size(var)
        else:
            # this should never happen
            raise InternalError('getattr: unexpected path {}'.format(path))
        return statdict

    def getxattr(self, name):
        return 'foo'

    def readdir(self, path):
        """Overrides readdir.
        Called when ls or ll and any other unix command that relies
        on this operation to work.
        """
        log_call()
        path = path.lstrip("/")
        if path == "":
            # Return a list of netCDF variables
            return (['.', '..'] + [item.encode('utf-8')
                    for item in self.dataset.variables])
        elif path in self.dataset.variables:
            local_attrs = self.getncAttrs(path)
            return ['.', '..'] + local_attrs + ["DATA_REPR"]
        else:
            return ['.', '..']

    def access(self, mode):
        log_call()
        if self.dataset_file is not None:
            path = self.dataset_file
            # If we can execute it, we should be able to read it too
            if mode == os.X_OK:
                mode = os.R_OK
        if not os.access(path, mode):
            raise FuseOSError(EACCES)

    def open(self, path, flags):
        log_call()
        if not self.is_file(path):
            raise FuseOSOSError('not a file')
        return 0

    def read(self, path, size, offset):
        log_call()
        if self.is_var_attribute(path):
            varname = self.get_varname(path)
            attrname = self.get_attrname(path)
            attr = self.get_attribute(path)
            return self.attr_repr(attr)[offset:offset+size]
        elif self.is_var_data(path):
            var = self.get_variable(path)
            return self.vardata_repr(var)[offset:offset+size]
        else:
            #This should never happen
            raise InternalError('read: unexpected path {}'.format(path))

    def write(self, path, data, offset):
        #TODO: to be implemented
        return len(data)

    def close(self, fh):
        log_call()



class NCFSOperations(Operations):
    """Inherit from the base fusepy Operations class"""

    def __init__(self, ncfs):
        self.ncfs = ncfs

    """These are the fusepy module methods that are overridden
    in this class. Any method not overridden here means that
    the default fusepy API method will be used.

    (See the fusepy.Operations class)

    Note these are not exactly the same as the C libs for FUSE

    """
    def acccess(self, path, mode):
        self.ncfs.access(mode)

    def read(self, path, size, offset, fh):
        return self.ncfs.read(path, size, offset)

    def write(self, path, data, offset, fh):
        return self.ncfs.write(path, data, offset)

    def getattr(self, path, fh=None):
        return self.ncfs.getattr(path)

    def getxattr(self, path, name):
        return self.ncfs.getxattr(name)

    def listxattr(self, path):
        return self.ncfs.listxattr()

    def readdir(self, path, fh):
        return self.ncfs.readdir(path)

    def release(self, path, fh):
        return self.ncfs.close(fh)

    def statfs(self, path):
        # Need to think about this one some more...
        stv = os.statvfs(path)
        return dict(
            (key, getattr(stv, key)) for key in (
             'f_bavail', 'f_bfree',
             'f_blocks', 'f_bsize', 'f_favail', 'f_ffree', 'f_files',
             'f_flag', 'f_frsize', 'f_namemax'))

    def open(self, path, flags):
        return self.ncfs.open(path, flags)

    truncate = None
    rename = None
    symlink = None
    setxattr = None
    removexattr = None
    link = None
    mkdir = None
    mknod = None
    rmdir = None
    unlink = None
    chmod = None
    chown = None
    create = None
    fsync = None
    flush = None



def log_call():
    """print current function name and function arguments"""
    # Get the previous frame in the stack, otherwise it would be this function!!!
    prev_frame = inspect.currentframe().f_back
    func_name = prev_frame.f_code.co_name
    func_args = inspect.getargvalues(prev_frame).locals
    func_args = ','.join(['{}={}'.format(k, repr(v)) for k, v in func_args.iteritems()])
    # Dump the message + the name of this function to the log.
    log.debug("%s(%s)" % (func_name, func_args))



def main():
    """
    This function is our Composition Root & we are using Pure DI (a.k.a.
    Poor Man's DI) - Ideally, this is the only place where we create all
    objects and wire everything together. This is the only place where
    global config params and commandline params/options are needed.

    http://blog.ploeh.dk/2011/07/28/CompositionRoot/ - great stuff
    on how to keep everything decoupled and write unit-testable code.
    """

    # Read config file, commandline parameters, options

    parser = argparse.ArgumentParser(
            description = 'Mount NetCDF filesystem',
            prog ='fusenetcdf')

    parser.add_argument(
            dest = 'ncpath',
            metavar = 'PATH',
            help = 'NetCDF file to be mounted')

    parser.add_argument(
            dest = 'mountpoint',
            metavar = 'DIR',
            help = 'mount point directory (must exist)')

    parser.add_argument(
            '-v',
            dest = 'verbosity_level',
            action ='count',
            default = 0,
            help = 'be verbose (-vv for debug messages)')

    cmdline = parser.parse_args()

    # setup logging

    if cmdline.verbosity_level == 1:
        loglevel = log.INFO
    elif cmdline.verbosity_level >= 2:
        loglevel = log.DEBUG
    else:
        loglevel = None
    if loglevel is not None:
        log.basicConfig(format='%(message)s', level=loglevel)

    # build the application

    dataset = ncpy.Dataset(cmdline.ncpath, 'r')
    # create plugins for generating data and atribute representations
    vardata_repr = VardataAsFlatTextFiles(fmt='%f')
    attr_repr = AttributesAsTextFiles()
    # create main object implementing NetCDF filesystem functionality
    ncfs = NCFS(dataset, vardata_repr, attr_repr)
    # create FUSE Operations (does it need to be a separate class?)
    ncfs_operations = NCFSOperations(ncfs)

    # launch!
    fuse = FUSE(ncfs_operations, cmdline.mountpoint,
            nothreads=True, foreground=True)



if __name__ == "__main__":
    main()

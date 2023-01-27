#!/usr/bin/env python3

#
# (c) 2022 Robert Bosch GmbH
# (c) 2023 Real Time Innovations, Inc.
#
# All files and artifacts in this repository are licensed under the
# provisions of the license provided by the LICENSE file in this repository.
#
#
# Convert vspec files to DDS-IDL
#

from email.policy import default
import sys
import vspec
import argparse
import keyword
import hashlib      # [neil-rti] for de-duplication of struct types
import json         # [neil-rti] temporary for pretty-printing

from vspec.model.vsstree import VSSNode, VSSType

def add_arguments(parser: argparse.ArgumentParser):
   parser.description="The DDS-IDL exporter"
   parser.add_argument('--all-idl-features', action='store_true',
                        help='Generate all features based on DDS IDL 4.2 specification')

c_keywords = [
    "auto"   , "break", "case"    , "char", "const"   , "continue", "default", "do"   , "double", "else"  , "enum"  , "extern", "float",
    "for"    , "goto" , "if"      , "int" , "long"    , "register",  "return", "short", "signed", "sizeof", "static", "struct", "switch",
    "typedef","union" , "unsigned", "void", "volatile", "while"
    ]

#Based on http://www.omg.org/spec/IDL/4.2/
idl_keywords =[
    "abstract" ,"any"      ,"alias" ,"attribute","bitfield" ,"bitmask"   ,"bitset"   ,"boolean","case"       ,"char"    ,"component","connector" ,"const" ,
    "consumes" ,"context"  ,"custom","default"  ,"double"   ,"exception" ,"emits"    ,"enum"   ,"eventtype"  ,"factory" ,"FALSE"    ,"finder"    ,"fixed" ,
    "float"    ,"getraises","home"  ,"import"   ,"in"       ,"inout"     ,"interface","local"  ,"long"       ,"manages" ,"map"      ,"mirrorport","module","multiple",
    "native"   ,"Object"   ,"octet" ,"oneway"   ,"out"      ,"primarykey","private"  ,"port"   ,"porttype"   ,"provides","public"   ,"publishes" ,"raises","readonly",
    "setraises","sequence" ,"short" ,"string"   ,"struct"   ,"supports"  ,"switch"   ,"TRUE"   ,"truncatable","typedef" ,"typeid"   ,"typename"  ,"typeprefix",
    "unsigned" ,"union"    ,"uses"  ,"ValueBase","valuetype","void"      ,"wchar"    ,"wstring","int8"       ,"uint8"   ,"int16"    ,"int32"     ,
    "int64"    ,"uint16"   ,"uint32","uint64"
    ]

def getAllowedName(name):
    if(
        name.lower() in c_keywords
        or name.lower() in idl_keywords 
        or keyword.iskeyword(name.lower)
    ):
        return "_"+name
    else:
        return name

idlFileBuffer = []

dataTypesMap_covesa_dds={"uint8": "octet",
              "int8": "octet",
              "uint16": "unsigned short",
              "int16": "short",
              "uint32": "unsigned long",
              "int32": "long",
              "uint64": "unsigned long long",
              "int64": "long long",
              "boolean": "boolean",
              "float": "float",
              "double": "double",
              "string": "string"
              }

# build-up the grouped elements into types here
idlGroupedTypes = {}

# module/namespace path 
modulePath = []

def collect_node( node, generate_uuid,generate_all_idl_features):
    """
    This method will traverse VSS nodes and collect data types into the idlGroupedTypes container
    """
    global idlGroupedTypes
    global modulePath
    # old:
    global idlFileBuffer
    datatype = None
    unit=None
    min=None
    max=None
    defaultValue=None
    allowedValues=None
    arraysize=None

    if node.type == VSSType.BRANCH:
        modulePath.append(getAllowedName(node.name))
        for child in node.children:
            collect_node( child, generate_uuid,generate_all_idl_features)
        modulePath.pop(-1)

    else:
        # add a node for this module nesting if needed
        if str(":".join(modulePath)) not in idlGroupedTypes:
            idlGroupedTypes[str(":".join(modulePath))] = {}

        # add a node for this member
        idlGroupedTypes[str(":".join(modulePath))][getAllowedName(node.name)] = {}

        # add the member elements
        idlGroupedTypes[str(":".join(modulePath))][getAllowedName(node.name)]["vsstype"] = node.type.value
        if node.datatype != "":
            idlGroupedTypes[str(":".join(modulePath))][getAllowedName(node.name)]["datatype"] = node.datatype.value
        if node.allowed != "":
            idlGroupedTypes[str(":".join(modulePath))][getAllowedName(node.name)]["allowed"] = node.allowed
        if node.default != "":
            idlGroupedTypes[str(":".join(modulePath))][getAllowedName(node.name)]["default"] = node.default
        if node.min != "":
            idlGroupedTypes[str(":".join(modulePath))][getAllowedName(node.name)]["min"] = node.min
        if node.max != "":
            idlGroupedTypes[str(":".join(modulePath))][getAllowedName(node.name)]["max"] = node.max
        try:
            idlGroupedTypes[str(":".join(modulePath))][getAllowedName(node.name)]["unit"] = node.unit.value
        except AttributeError:
            pass
        if node.description != "":
            idlGroupedTypes[str(":".join(modulePath))][getAllowedName(node.name)]["description"] = node.description
        if node.comment != "":
            idlGroupedTypes[str(":".join(modulePath))][getAllowedName(node.name)]["comment"] = node.comment

def post_process_idl(generate_all_idl_features):
    """
    This method creates common struct types
    """
    global idlGroupedTypes
    finalTypes = {}

    # first-level: consolidate into structs.
    for modgroup in idlGroupedTypes:
        # loop-thru and create a hash of the name and select member elements
        mh = hashlib.sha1()
        for itemName, itemElements in idlGroupedTypes[modgroup].items():
            # for each member, include its name..
            mh.update(itemName.encode('utf-8'))
            # vsstype
            mh.update(itemElements["vsstype"].encode('utf-8'))
            # datatype
            mh.update(itemElements["datatype"].encode('utf-8'))
            # allowed (if present)
            if "allowed" in itemElements:
                mh.update(','.join(itemElements["allowed"]).encode('utf-8'))

            # other elements (if present)
            if "default" in itemElements:
                mh.update(str(itemElements["default"]).encode('utf-8'))
            if "min" in itemElements:
                mh.update(str(itemElements["min"]).encode('utf-8'))
            if "max" in itemElements:
                mh.update(str(itemElements["max"]).encode('utf-8'))
            if "unit" in itemElements:
                mh.update(itemElements["unit"].encode('utf-8'))
            if "comment" in itemElements:
                mh.update(itemElements["comment"].encode('utf-8'))
            # NOTE: sometimes the description is slightly different on otherwise identical structs.  Omit?
            #if "description" in itemElements:
            #    mh.update(itemElements["description"].encode('utf-8'))

        hashOfElementsAndNames = mh.hexdigest()

        # add or update the finalTypes dict
        if hashOfElementsAndNames in finalTypes:
            # this struct is already in place; add this instances module path to it
            finalTypes[hashOfElementsAndNames]["paths"].append(modgroup)
        else:
            # create a new record for this struct
            finalTypes[hashOfElementsAndNames] = {}
            #finalTypes[hashOfElementsAndNames]["name"] = structName
            finalTypes[hashOfElementsAndNames]["paths"] = [modgroup]
            finalTypes[hashOfElementsAndNames]["members"] = idlGroupedTypes[modgroup]

    # Test: print as structs
    for dType in finalTypes:
        structName = ""
        pathList = []       # path to struct
        varList = []        # if multi-paths, this is a list of vars in the path
        pathCount = len(finalTypes[dType]["paths"])
        if pathCount > 1:
            # find the different parts of these paths
            refPathList = finalTypes[dType]["paths"][0].split(":")
            diffPathIdxList = []

            # compare path[0] to the others in the list to find all the changed parts
            for i in range(1, pathCount):
                tmpPathList = finalTypes[dType]["paths"][i].split(":")
                # compare each item in the path; if same, 
                for j in range(min(len(tmpPathList), len(refPathList))):
                    if tmpPathList[j] != refPathList[j] and j not in diffPathIdxList:
                        diffPathIdxList.append(j)
            
            # now make the common path and list of diffs
            diffPathIdxList.sort()
            for i in range(pathCount):
                tmpPathList = finalTypes[dType]["paths"][i].split(":")
                tmpDiffList = []
                for idx in diffPathIdxList:
                    if idx < len(tmpPathList):
                        tmpDiffList.append(tmpPathList[idx])
                varList.append(":".join(tmpDiffList))
            diffPathIdxList.sort(reverse = True)
            for idx in diffPathIdxList:
                refPathList.pop(idx)
            pathList = refPathList
        
        else:
            # single-path structs
            pathList = finalTypes[dType]["paths"][0].split(":")
            if len(pathList) == 1:
                pathList.append("State")

        structName = pathList[-1]
        print("P: {}, S: {}, V: {}, members: {}".format(":".join(pathList[0:-1]), structName, varList, len(finalTypes[dType]["members"])))
        print(json.dumps(finalTypes[dType]["members"], indent=2))





def export_node( node, generate_uuid,generate_all_idl_features):
    """
    This method is used to traverse VSS node and to create corresponding DDS IDL buffer string
    """
    global idlFileBuffer
    datatype = None
    unit=None
    min=None
    max=None
    defaultValue=None
    allowedValues=None
    arraysize=None

    if node.type == VSSType.BRANCH:
        idlFileBuffer.append("module "+getAllowedName(node.name))
        idlFileBuffer.append("{")
        for child in node.children:
            export_node( child, generate_uuid,generate_all_idl_features)
        idlFileBuffer.append("};")
        idlFileBuffer.append("")
    else:
        isEnumCreated=False
        #check if there is a need to create enum (based on the usage of allowed values)
        if node.allowed!="":
            """
            enum should be enclosed under module block to avoid namespec conflict
            module name for enum is chosen as the node name + 
            """
            if (node.datatype.value in ["string", "string[]"]):
                idlFileBuffer.append("module "+getAllowedName(node.name)+"_M")
                idlFileBuffer.append("{")
                idlFileBuffer.append("enum "+getAllowedName(node.name)+"Values{"+str(",".join(node.allowed))+"};")
                isEnumCreated=True
                idlFileBuffer.append("};")
                allowedValues=str(node.allowed)
            else:
                print(f"Warning: VSS2IDL can only handle allowed values for string type, signal {node.name} has type {node.datatype.value}")

        idlFileBuffer.append("struct "+getAllowedName(node.name))
        idlFileBuffer.append("{")
        #if generate_uuid:
        #    idlFileBuffer.append("string uuid;")
        #fetching value of datatype and obtaining the equivalent DDS type
        try:
            if str(node.datatype.value) in dataTypesMap_covesa_dds:
                datatype= str(dataTypesMap_covesa_dds[str(node.datatype.value)])
            elif '[' in str(node.datatype.value):
                nodevalueArray=str(node.datatype.value).split("[",1)
                if str(nodevalueArray[0]) in dataTypesMap_covesa_dds :
                    datatype= str(dataTypesMap_covesa_dds[str(nodevalueArray[0])])
                    arraysize='['+str(arraysize)+nodevalueArray[1]

        except AttributeError:
            pass
        #fetching value of unit
        try:
            unit =str(node.unit.value)
        except AttributeError:
            pass

        if node.min!="":
            min=str(node.min)
        if node.max!="":
            max=str(node.max)
        if node.default != "":
            defaultValue=node.default
            if isinstance(defaultValue,str) and isEnumCreated==False:
                defaultValue="\""+defaultValue+"\""


        if datatype !=None:
            #adding range if min and max are specified in vspec file
            if min!=None and max!=None and generate_all_idl_features:
                idlFileBuffer.append("@range(min="+str(min)+" ,max="+str(max)+")")

            if allowedValues == None:
                if defaultValue==None:
                    idlFileBuffer.append(("sequence<"+datatype+"> value" if arraysize!=None else datatype+" value")+";" )
                else:
                    #default values in IDL file are not accepted by CycloneDDS/FastDDS : these values can be generated if --all-idl-features is set as True
                    idlFileBuffer.append(("sequence<"+datatype+"> value" if arraysize!=None else datatype+" value")+
                                        ("  default "+str(defaultValue) if generate_all_idl_features else "") +";")
            else:
                #this is the case where allowed values are provided, accordingly contents are converted to enum
                if defaultValue==None:
                    idlFileBuffer.append(getAllowedName(node.name)+"_M::"+getAllowedName(node.name)+"Values value;")
                else:
                    #default values in IDL file are not accepted by CycloneDDS/FastDDS : these values can be generated if --all-idl-features is set as True
                    idlFileBuffer.append(getAllowedName(node.name)+"_M::"+getAllowedName(node.name)+"Values value"+ (" "+str(defaultValue) if generate_all_idl_features else "")+";")


        #if unit!=None:
        #    idlFileBuffer.append(("" if generate_all_idl_features else "//")+"const string unit=\""+unit +"\";")

        #idlFileBuffer.append(("" if generate_all_idl_features else "//")+"const string type =\""+  str(node.type.value)+"\";")
        #idlFileBuffer.append(("" if generate_all_idl_features else "//")+"const string description=\""+  node.description+"\";")
        idlFileBuffer.append("};")


def export_idl(file, root, generate_uuids=True, generate_all_idl_features=False):
    """This method is used to traverse through the root VSS node to build
       -> DDS IDL equivalent string buffer and to serialize it acccordingly into a file
    """
    collect_node( root, generate_uuids,generate_all_idl_features)
    post_process_idl(generate_all_idl_features)

    # file.write('\n'.join(idlFileBuffer))
    print("IDL file generated at location : "+file.name)
    #print(json.dumps(idlGroupedTypes, indent=2))
    #for group in idlGroupedTypes:
    #    print(group)
    #    print("---------")




def export(config: argparse.Namespace, root: VSSNode, print_uuid):
    print("Generating DDS-IDL output...")
    idl_out=open(config.output_file,'w')
    export_idl(idl_out, root, print_uuid, config.all_idl_features)
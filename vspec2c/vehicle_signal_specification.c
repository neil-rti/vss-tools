// (C) 2016 Jaguar Land Rover
//
// All files and artifacts in this repository are licensed under the
// provisions of the license provided by the LICENSE file in this repository.
//
// Support code to access a vehicle signal specification from
// a C/C++ application
//
#include <string.h>
#include <stdio.h>
#include <vehicle_signal_specification.h>


const char* vss_element_type_string(vss_element_type_e elem_type)
{
    switch(elem_type) {
    case VSS_ATTRIBUTE: return "attribute";
    case VSS_BRANCH: return "branch";
    case VSS_SENSOR: return "sensor";
    case VSS_ACTUATOR: return "actuator";
    case VSS_RBRANCH: return "rbranch";
    case VSS_ELEMENT: return "element";
    default: return "*unknown*";
    }
}

const char* vss_data_type_string(vss_data_type_e data_type)
{
    switch(data_type) {
    case VSS_INT8: return "INT8";
    case VSS_UINT8: return "UINT8";
    case VSS_INT16: return "INT16";
    case VSS_UINT16: return "uint16";
    case VSS_INT32: return "int32";
    case VSS_UINT32: return "uint32";
    case VSS_DOUBLE: return "double";
    case VSS_FLOAT: return "float";
    case VSS_BOOLEAN: return "boolean";
    case VSS_STRING: return "string";
    case VSS_STREAM: return "stream";
    case VSS_NA: return "na";
    default: return "*unknown*";
    }
}

int vss_get_signal_count(void)
{
    // Defined by header file generated by vspec2c.py
    extern const int vss_signal_count;
    return vss_signal_count;
}

const char* vss_get_sha256_signature(void)
{
    // Defined by header file generated by vspec2c.py
    extern const char* vss_sha256_signature;
    return vss_sha256_signature;
}



vss_signal_t* vss_get_signal_by_index(int index)
{
    if (index < 0 || index >= vss_get_signal_count())
        return 0;

    return &vss_signal[index];
}

int vss_get_signal_by_path(char* path,
                            vss_signal_t ** result)
{
    vss_signal_t * cur_signal = &vss_signal[0]; // Start at root.
    char *path_separator = 0;

    if (!path || !result)
        return EINVAL;

    // Ensure that first element in root matches
    path_separator = strchr(path, '.');

    // If we found a path component separator, nil it out and
    // move to the next char after the separator
    // If no separator is found, path_separator == NULL, allowing
    // us to detect end of path
    if (strncmp(cur_signal->name, path, path_separator?path_separator-path:strlen(path))) {
        printf("Root signal mismatch between %s and %*s\\n",
               cur_signal->name,
               (int)(path_separator?path_separator-path:strlen(path)), path);
        return ENOENT;
    }

    if (path_separator)
        path_separator++;

    path = path_separator;

    while(path) {
        int ind = 0;
        path_separator = strchr(path, '.');
        int path_len = path_separator?path_separator-path:strlen(path);

        // We have to go deeper into the tree. Is our current
        // signal a branch that we can traverse into?
        if (cur_signal->element_type != VSS_BRANCH) {
            printf ("signal %*s is not a branch under %s. ENODIR\\n",
                     path_len, path, cur_signal->name);
            return ENOTDIR;
        }

        // Step through all children and check for a path componment match.
        while(cur_signal->children[ind]) {
            if (!strncmp(path, cur_signal->children[ind]->name, path_len) &&
                strlen(cur_signal->children[ind]->name) == path_len)
                break;

            ind++;
        }
        if (!cur_signal->children[ind]) {
            printf ("Child %*s not found under %s. ENOENT\\n",
                     path_len, path, cur_signal->name);

            return ENOENT;
        }
        cur_signal = cur_signal->children[ind];

        // If we found a path component separator, nil it out and
        // move to the next char after the separator
        // If no separator is found, path_separator == NULL, allowing
        // us to detect end of path
        if (path_separator)
            path_separator++;

        path = path_separator;
    }

    *result = cur_signal;

    return 0;
}

#define Py_LIMITED_API 0x030C0000
#include <Python.h>

/* 独立原型：整列输入，只使用稳定公开 C API，不读取 NumPy 私有结构。 */
static int validate(PyObject *kind, PyObject *names) {
    if (!PyType_Check(kind)) { PyErr_SetString(PyExc_TypeError,"record class required"); return -1; }
    if (!PyTuple_CheckExact(names)) { PyErr_SetString(PyExc_TypeError,"field names must be an exact tuple"); return -1; }
    PyObject *module=PyImport_ImportModule("doribt.accounting.records");
    if (!module) return -1;
    PyObject *guard=PyObject_GetAttrString(module,"_plain_record"); Py_DECREF(module);
    if (!guard) return -1;
    PyObject *answer=PyObject_CallFunctionObjArgs(guard,kind,NULL); Py_DECREF(guard);
    if (!answer) return -1;
    int valid=PyObject_IsTrue(answer); Py_DECREF(answer);
    if (valid<0) return -1;
    if (!valid) { PyErr_SetString(PyExc_TypeError,"unsupported record class"); return -1; }
    module=PyImport_ImportModule("dataclasses"); if (!module) return -1;
    PyObject *function=PyObject_GetAttrString(module,"fields"); Py_DECREF(module);
    if (!function) return -1;
    PyObject *fields=PyObject_CallFunctionObjArgs(function,kind,NULL); Py_DECREF(function);
    if (!fields) return -1;
    if (!PyTuple_Check(fields)) { Py_DECREF(fields); PyErr_SetString(PyExc_TypeError,"dataclass fields tuple required"); return -1; }
    Py_ssize_t width=PyTuple_Size(fields);
    if (width!=PyTuple_Size(names)) { Py_DECREF(fields); PyErr_SetString(PyExc_ValueError,"incomplete fields"); return -1; }
    for (Py_ssize_t col=0;col<width;col++) {
        PyObject *name=PyTuple_GetItem(names,col);
        if (!PyUnicode_CheckExact(name)) { Py_DECREF(fields); PyErr_SetString(PyExc_TypeError,"field name must be an exact string"); return -1; }
        PyObject *expected=PyObject_GetAttrString(PyTuple_GetItem(fields,col),"name");
        if (!expected) { Py_DECREF(fields); return -1; }
        int equal=PyUnicode_Compare(name,expected); Py_DECREF(expected);
        if (equal!=0) { Py_DECREF(fields); if (!PyErr_Occurred()) PyErr_SetString(PyExc_ValueError,"wrong field order"); return -1; }
    }
    Py_DECREF(fields); return 0;
}

static PyObject *bulk_columns(PyObject *self, PyObject *args) {
    PyObject *kind,*names,*columns;
    if (!PyArg_ParseTuple(args,"OOO",&kind,&names,&columns)) return NULL;
    if (validate(kind,names)<0) return NULL;
    if (!PyTuple_CheckExact(columns)) { PyErr_SetString(PyExc_TypeError,"columns must be an exact tuple"); return NULL; }
    Py_ssize_t width=PyTuple_Size(names);
    if (PyTuple_Size(columns)!=width || width==0) { PyErr_SetString(PyExc_ValueError,"wrong column count"); return NULL; }
    Py_ssize_t count=-1;
    for (Py_ssize_t col=0;col<width;col++) {
        PyObject *column=PyTuple_GetItem(columns,col);
        if (!PyList_CheckExact(column) && !PyTuple_CheckExact(column)) { PyErr_SetString(PyExc_TypeError,"each column must be an exact list or tuple"); return NULL; }
        Py_ssize_t length=PySequence_Size(column);
        if (length<0) return NULL;
        if (count<0) count=length;
        else if (count!=length) { PyErr_SetString(PyExc_ValueError,"unequal column lengths"); return NULL; }
    }
    /* args 持有不可变外层 tuple，其元素持有各列；整个构造期间保持 GIL。 */
    PyObject *result=PyTuple_New(count);
    if (!result) return NULL;
    PyObject *dict_name=PyUnicode_FromString("__dict__");
    if (!dict_name) { Py_DECREF(result); return NULL; }
    for (Py_ssize_t row=0;row<count;row++) {
        PyObject *record=PyType_GenericAlloc((PyTypeObject *)kind,0);
        if (!record) goto failure;
        PyObject *dictionary=PyObject_GenericGetAttr(record,dict_name);
        if (!dictionary) { Py_DECREF(record); goto failure; }
        if (!PyDict_Check(dictionary)) { Py_DECREF(dictionary); Py_DECREF(record); PyErr_SetString(PyExc_TypeError,"record dictionary required"); goto failure; }
        for (Py_ssize_t col=0;col<width;col++) {
            PyObject *value=PySequence_GetItem(PyTuple_GetItem(columns,col),row);
            if (!value) { Py_DECREF(dictionary); Py_DECREF(record); goto failure; }
            int status=PyDict_SetItem(dictionary,PyTuple_GetItem(names,col),value);
            Py_DECREF(value);
            if (status<0) { Py_DECREF(dictionary); Py_DECREF(record); goto failure; }
        }
        Py_DECREF(dictionary);
        if (PyTuple_SetItem(result,row,record)<0) goto failure;
    }
    Py_DECREF(dict_name); return result;
failure:
    Py_DECREF(dict_name); Py_DECREF(result); return NULL;
}
static PyMethodDef methods[]={{"bulk_columns",bulk_columns,METH_VARARGS,"Create complete eager records from validated columns."},{NULL,NULL,0,NULL}};
static struct PyModuleDef module={PyModuleDef_HEAD_INIT,"doribt._native_records",NULL,-1,methods};
PyMODINIT_FUNC PyInit__native_records(void) {
    PyObject *value=PyModule_Create(&module);
    if (!value) return NULL;
    if (PyModule_AddIntConstant(value,"API_VERSION",1)<0) { Py_DECREF(value); return NULL; }
    return value;
}

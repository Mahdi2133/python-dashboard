# -*- coding: utf-8 -*-
"""The reporting layer: data sources → query engine → formulas → renderers.

    catalogue  what can be reported on, built from the form and process
               builders at run time (nothing here knows a particular form)
    formula    a safe expression language for calculated fields
    engine     filters, groupings, aggregations, KPIs, charts, tables,
               drill-down and analysis over a data source
    access     who may see which report, and never more than the data allows
    exports    Excel, PDF, Word, CSV, JSON, HTML from the same definition
"""

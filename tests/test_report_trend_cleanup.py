from catalyst.reports import simplify_trend_sheet


class FakeRange:
    def __init__(self, worksheet, address):
        self.worksheet = worksheet
        self.address = address

    def ClearContents(self):
        self.worksheet.cleared.append(self.address)


class FakeRows:
    def __init__(self, worksheet, address):
        self.worksheet = worksheet
        self.address = address

    @property
    def Hidden(self):
        return None

    @Hidden.setter
    def Hidden(self, value):
        self.worksheet.hidden.append((self.address, value))


class FakeChart:
    def __init__(self):
        self.PlotVisibleOnly = True


class FakeChartObject:
    def __init__(self):
        self.Chart = FakeChart()


class FakeChartObjects:
    def __init__(self, count):
        self.items = [FakeChartObject() for _ in range(count)]
        self.Count = count

    def Item(self, index):
        return self.items[index - 1]


class FakeWorksheet:
    def __init__(self, chart_count):
        self.cleared = []
        self.hidden = []
        self.chart_objects = FakeChartObjects(chart_count)

    @property
    def charts(self):
        return [item.Chart for item in self.chart_objects.items]

    def Range(self, address):
        return FakeRange(self, address)

    def Rows(self, address):
        return FakeRows(self, address)

    def ChartObjects(self):
        return self.chart_objects


def test_simplify_trend_sheet_hides_sources_and_keeps_hidden_chart_data():
    worksheet = FakeWorksheet(chart_count=2)

    simplify_trend_sheet(worksheet)

    assert worksheet.cleared == ['B66:AT148']
    assert worksheet.hidden == [('30:148', True)]
    assert [chart.PlotVisibleOnly for chart in worksheet.charts] == [False, False]

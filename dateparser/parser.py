# coding: utf-8
import calendar
import re

from io import StringIO
from collections import OrderedDict
from datetime import datetime
from datetime import timedelta


NSP_COMPATIBLE = re.compile(r'\D')


def no_space_parser_eligibile(datestring):
    return not bool(NSP_COMPATIBLE.search(datestring))


def get_unresolved_attrs(parser_object):
    attrs = ['year', 'month', 'day']
    seen = []
    unseen = []
    for attr in attrs:
        if getattr(parser_object, attr, None) is not None:
            seen.append(attr)
        else:
            unseen.append(attr)
    return seen, unseen


def resolve_date_order(order):
    chart = {
        'MDY': {'day': False, 'year': False},
        'YMD': {'day': False, 'year': True},
        'YDM': {'day': True, 'year': True},
        'DMY': {'day': True, 'year': False},
    }
    return chart[order]


def parse(datestring, settings):
    exceptions = []
    for parser in [_parser.parse, _no_spaces_parser.parse]:
        try:
            res = parser(datestring, settings)
            if res:
                return res
        except Exception as e:
            exceptions.append(e)
    else:
        raise exceptions.pop(-1)


class _no_spaces_parser(object):
    _dateformats = [
        '%Y%m%d', '%Y%d%m', '%m%Y%d',
        '%m%d%Y', '%d%Y%m', '%d%m%Y',
        '%y%m%d', '%y%d%m', '%m%y%d',
        '%m%d%y', '%d%y%m', '%d%m%y'
    ]

    period = {
        'day': ['%d', '%H', '%M', '%S'],
        'month': ['%m']
    }

    def __init__(self, *args, **kwargs):
        self._timeformats = ['%H', '%H%M', '%H%M%S']

        self._all = (self._dateformats + 
                     [x+y for x in self._dateformats for y in self._timeformats] +
                     self._timeformats)

        date_formats = {
            (False, False): self._all,
            (True, False): [x for x in self._all if x.lower().startswith('%y')],
            (False, True): [x for x in self._all if '%d%m' in x],
            (True, True): [x for x in self._all if x.lower().startswith('%y%d')],
        }

    @classmethod
    def _get_period(cls, format_string):
        for pname, pdrv in cls.period.items():
            for drv in pdrv:
                if drv in format_string:
                    return pname
        else:
            return 'year'

    @classmethod
    def parse(cls, datestring, settings):
        if not no_space_parser_eligibile(datestring):
            return

        datestring = datestring.replace(':', '')
        tokens = tokenizer(datestring)
        order = resolve_date_order(settings.DATE_ORDER)
        nsp = cls()
        for token, _ in tokens.tokenize():
            for fmt in nsp.date_formats[(order['year'], order['day'])]:
                try:
                    return datetime.strptime(token, fmt), cls._get_period(fmt)
                except:
                    pass
        else:
            raise ValueError('Unable to parse date from: %s' % datestring)


class _parser(object):

    alpha_directives = OrderedDict([
        ('weekday', ['%A', '%a']),
        ('month', ['%B', '%b']),
    ])

    time_directives = ['%p']

    num_directives = OrderedDict([
        ('month', ['%m']),
        ('day', ['%d']),
        ('year', ['%y', '%Y']),
        ('time', ['%H:%M:%S', '%H:%M', '%I:%M:%S', '%I:%M']),
    ])

    deltas = {
        'pm': timedelta(hours=12),
    }

    def _get_year(self, token):
        for directive in self.num_directives['year']:
            try:
                do = datetime.strptime(token, directive)
                self._token_year = token
                return do.year
            except:
                pass

    def _get_day(self, token):
        for directive in self.num_directives['day']:
            try:
                do = datetime.strptime(token, directive)
                self._token_day = token
                return do.day
            except:
                pass

    def _get_month(self, token):
        for directive in self.num_directives['month']:
            try:
                do = datetime.strptime(token, directive)
                self._token_month = token
                return do.month
            except:
                pass

    def _get_component_token(self, key):
        return getattr(self, '_token_%s' % key, None)

    def __init__(self, tokens, settings):
        self.settings = settings

        self.unset_tokens = []

        self.day = None
        self.month = None
        self.year = None
        self.time = None
        self.delta = timedelta(0)

        self.auto_order = []

        self._token_day = None
        self._token_month = None
        self._token_year = None
        self._token_time = None
        self._token_delta = None

        for token, type in tokens:
            if type <= 1:
                if token in settings.SKIP_TOKENS_PARSER:
                    continue
                results = self._parse(type, token, settings.FUZZY)
                for res in results:
                    setattr(self, *res)

        known, unknown = get_unresolved_attrs(self)
        params = {}
        for attr in known:
            params.update({attr: getattr(self, attr)})
        for attr in unknown:
            for token, type, _ in self.unset_tokens:
                if type == 0:
                    params.update({attr: int(token)})
                    datetime(**params)
                    setattr(self, '_token_%s' % attr, token)
                    setattr(self, attr, token)

        self.apply_date_order(**resolve_date_order(settings.DATE_ORDER))

    def apply_date_order(self, year=False, day=False):
        if not year and not day:
            return

        def swap(key1, key2):
            if not(key1 in self.auto_order and key2 in self.auto_order):
                return

            index1 = self.auto_order.index(key1)
            index2 = self.auto_order.index(key2)
            if index1 > index2:
                old_val1, old_val2 = self._get_component_token(key1), \
                    self._get_component_token(key2)

                setattr(self, key1, getattr(self, '_get_%s' % key1)(old_val2))
                setattr(self, key2, getattr(self, '_get_%s' % key2)(old_val1))

                self.auto_order[index1] = key2
                self.auto_order[index2] = key1
        if yearfirst:
            swap('year', 'month')
            swap('month', 'day')

        if dayfirst:
            swap('day', 'month')


    def _get_period(self):
        for period in ['time', 'day']:
            if getattr(self, period, None):
                return 'day'

        for period in ['month', 'year']:
            if getattr(self, period, None):
                return period

        if self._results():
            return 'day'

    def _results(self):
        self.now = self.settings.RELATIVE_BASE
        if not self.now:
            self.now = datetime.utcnow()

        time = self.time() if not self.time is None else None

        params = {
            'day': self.day or self.now.day,
            'month': self.month or self.now.month,
            'year': self.year or self.now.year,
            'hour': time.hour if time else 0,
            'minute': time.minute if time else 0,
            'second': time.second if time else 0,
        }

        try:
            return datetime(**params)
        except ValueError as e:
            error_text = getattr(e, 'message', None) or e.__str__()
            error_msgs = ['day is out of range', 'day must be in']
            if ((error_msgs[0] in error_text or error_msgs[1] in error_text) and
                not(self._token_day or hasattr(self, '_token_weekday'))
                ):
                _, tail = calendar.monthrange(params['year'], params['month'])
                params['day'] = tail
                return datetime(**params)
            else:
                raise e

    def _correct_for_time_frame(self, dateobj):
        days = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']

        token_weekday, _ = getattr(self, '_token_weekday', (None, None))

        if token_weekday and not(self._token_year or self._token_month or self._token_day):
            day_index = calendar.weekday(dateobj.year, dateobj.month, dateobj.day)
            day = token_weekday[:3].lower()
            steps = 0
            if 'future' in self.settings.PREFER_DATES_FROM:
                if days[day_index] == day:
                    steps = 7
                else:
                    while days[day_index] != day:
                        day_index = (day_index + 1) % 7
                        steps += 1
                delta = timedelta(days=steps)
            else:
                if days[day_index] == day:
                    steps = 7
                else:
                    while days[day_index] != day:
                        day_index -= 1
                        steps += 1
                delta = timedelta(days=-steps)

            dateobj = dateobj + delta

        if self.month and not self.year:
            if self.now < dateobj:
                if 'past' in self.settings.PREFER_DATES_FROM:
                    dateobj = dateobj.replace(year=dateobj.year - 1)
            else:
                if 'future' in self.settings.PREFER_DATES_FROM:
                    dateobj = dateobj.replace(year=dateobj.year + 1)

        if self._token_time and not any([self._token_year,
                                         self._token_month,
                                         self._token_day,
                                         hasattr(self, '_token_weekday')]):
            if 'past' in self.settings.PREFER_DATES_FROM:
                if self.now.time() < dateobj.time():
                    dateobj = dateobj + timedelta(days=-1)
            if 'future' in self.settings.PREFER_DATES_FROM:
                if self.now.time() > dateobj.time():
                    dateobj = dateobj + timedelta(days=1)

        return dateobj

    def _correct_for_day(self, dateobj):
        if (getattr(self, '_token_day', None) or
            getattr(self, '_token_weekday', None) or
            getattr(self, '_token_time', None)):
            return dateobj

        _, tail = calendar.monthrange(dateobj.year, dateobj.month)
        options = {
            'first': 1,
            'last': tail,
            'current': self.now.day
        }

        try:
            return dateobj.replace(day=options[self.settings.PREFER_DAY_OF_MONTH])
        except ValueError:
            return dateobj.replace(day=options['last'])

    @classmethod
    def parse(cls, datestring, settings):
        tokens = tokenizer(datestring)
        po = cls(tokens.tokenize(), settings)
        dateobj = po._results()

        if po.delta and po.time().hour <= 12:
            dateobj += po.delta

        # correction for past, future if applicable
        dateobj = po._correct_for_time_frame(dateobj)

        # correction for preference of day: beginning, current, end
        dateobj = po._correct_for_day(dateobj)

        return dateobj, po._get_period()

    def _parse(self, type, token, fuzzy, skip_component=None):

        def set_and_return(token, type, component, dateobj, skip_date_order=False):
            if not skip_date_order:
                self.auto_order.append(component)
            setattr(self, '_token_%s' % component, (token, type))
            return [(component, getattr(dateobj, component))]

        def parse_number(token, skip_component=None):
            type = 0

            for component, directives in self.num_directives.items():
                if skip_component == component:
                    continue
                for directive in directives:
                    try:
                        do = datetime.strptime(token, directive)
                        prev_value = getattr(self, component, None)
                        if not prev_value:
                            return set_and_return(token, type, component, do)
                        else:
                            try:
                                prev_token, prev_type = getattr(self, '_token_%s' % component)
                                if prev_type == type:
                                    do = datetime.strptime(prev_token, directive)
                            except ValueError:
                                self.unset_tokens.append((prev_token, prev_type, component))
                                return set_and_return(token, type, component, do)
                    except ValueError:
                        pass
            else:
                raise ValueError('Unable to parse: %s' % token)

        def parse_alpha(token, skip_component=None):
            type = 1

            for component, directives in self.alpha_directives.items():
                if skip_component == component:
                    continue
                for directive in directives:
                    try:
                        do = datetime.strptime(token, directive)
                        prev_value = getattr(self, component, None)
                        if not prev_value:
                            return set_and_return(token, type, component, do, skip_date_order=True)
                        elif component == 'month':
                            index = self.auto_order.index('month')
                            self.auto_order[index] = 'day'
                            setattr(self, '_token_day', self._token_month)
                            setattr(self, '_token_month', token)
                            return [(component, getattr(do, component)), ('day', prev_value)]
                    except:
                        pass
            else:
                for directive in self.time_directives:
                    try:
                        do = datetime.strptime(token, directive)
                        return [('delta', self.deltas.get(token.lower(), timedelta(0)))]
                    except:
                        pass
                if not fuzzy:
                    raise ValueError('Unable to parse: %s' % token)
                else:
                    return []

        handlers = {0: parse_number, 1: parse_alpha}
        return handlers[type](token, skip_component)


class tokenizer(object):
    digits = '0123456789:'
    letters = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
    nonwords = "./\()\"':,.;<>~!@#$%^&*|+=[]{}`~?-     "

    def _isletter(self, tkn): return tkn in self.letters
    def _isdigit(self, tkn): return tkn in self.digits
    def _isnonword(self, tkn): return tkn in self.nonwords

    def __init__(self, ds):
        self.instream = StringIO(ds)

    def _switch(self, chara, charb):
        if self._isdigit(chara):
            return 0, not self._isdigit(charb)

        if self._isletter(chara):
            return 1, not self._isletter(charb)

        if self._isnonword(chara):
            return 2, not self._isnonword(charb)

        return '', True

    def tokenize(self):
        token = ''
        EOF = False

        while not EOF:
            nextchar = self.instream.read(1)

            if not nextchar:
                EOF = True
                type, _ = self._switch(token[-1], nextchar)
                yield token, type
                return

            if token:
                type, switch = self._switch(token[-1], nextchar)

                if not switch:
                    token += nextchar
                else:
                    yield token, type
                    token = nextchar
            else:
                token += nextchar

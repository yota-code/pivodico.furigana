#!/usr/bin/env python3

import sys, collections

import reccipe

from reccipe.file import Path

import pivo
import pivo.lang.ja

from furigana.duplex import Duplex

class Ruby() :
	def __init__(self, explicit=True, debug=False) :

		self.explicit = explicit
		self.debug = debug

		self.furigana = dict()
		self.jukujikun = dict()

		self.f_longest = collections.defaultdict(int)

	def refresh_f_longest(self) :
		self.f_longest = {
			k : max(len(f) for f in self.furigana[k])
			for k in self.furigana
		}

	def default_config(self) :
		pth = Path(__file__).absolute()
		print(pth)

		self.furigana = reccipe.data.json_load(pivo.pth('data/lang/ja/furigana.json'))
		self.jukujikun = reccipe.data.json_load(pivo.pth('data/lang/ja/jukujikun.json'))
		self.refresh_f_longest()
		return self

	def _push_jukujikun(self, k, f) :
		if k not in self.jukujikun :
			m = self.jukujikun
			for c in reversed(k) :
				if c not in m :
					m[c] = dict()
				m = m[c]
			m[f] = None

	def load_jukujikun(self, pth) :
		"""
		complexe readings
		"""
		for k, * f_lst in reccipe.data.tsv_load(pth) :
			for f in f_lst :
				f = f.strip()
				if not f :
					continue
				self._push_jukujikun(k, f)

	def _push_furigana(self, k, f) :
		if k not in self.furigana :
			self.furigana[k] = dict()
		f, null, r = f.partition('/')
		f, null, o = f.strip('-').partition('.')
		f = pivo.lang.ja.to_hiragana(f)
		self.furigana[k][f] = r
		self.f_longest[k] = max(self.f_longest[k], len(f))

	def load_furigana(self, pth) :
		"""
		reading can contains:
		'-' to mark a suffix of prefix form
		'.' to mark the begining of okurigana
		"""
		for k, * f_lst in reccipe.data.tsv_load(pth) :
			for f in f_lst :
				self._push_furigana(k, f)

	def dbg(self, s, depth=0) :
		if self.debug :
			print('\t' * depth + s, file=sys.stderr)

	def match_jukujikun(self, w, i=None, j=None, depth=0) :
		i, j = w.seek(i, j)
		self.dbg(">>> Ruby.match_jukujikun({0}, {1}, {2}, {3})".format(
			w._k_original, w._f_original, i, j
		), depth=depth)
		m = self.jukujikun
		k, p = w.k_normal(i)
		while k in m :
			m = m[k]
			for a, b in m.items() :
				if b is None :
					f, q = w.f_normal(j, len(a))
					if a == f :
						result = w.original(i, j, i - p, len(a))
						self.dbg("<-- Ruby.match_jukujikun: {0!r}".format(result), depth=depth)
						yield result
			k, p = w.k_normal(p)

	def match_kanji(self, w, i=None, j=None, depth=0) :
		i, j = w.seek(i, j)
		self.dbg(">>> Ruby.match_kanji({0}, {1}, {2}, {3})".format(
			w._k_original, w._f_original, i, j
		), depth=depth)
		k, p = w.k_normal(i)
		if k in self.furigana :
			no_match_found = True
			for z in range(1, min(j, self.f_longest[k])+1) :
				f, q = w.f_normal(j, z)
				if f in self.furigana[k] :
					result = w.original(i, j, 1, z)
					self.dbg("<-- Ruby.match_kanji() {0!r}".format(result), depth=depth)
					no_match_found = False
					yield result
			if no_match_found :
				# pour l'instant, il n'y a que les match de kanji qui sont pris en charge
				yield from self.failed_match_kanji(w, i, j, depth)

	def match_kana(self, w, i=None, j=None, depth=0) :
		i, j = w.seek(i, j)
		self.dbg(">>> Ruby.match_kana({0}, {1}, {2}, {3})".format(
			w._k_original, w._f_original, i, j
		), depth=depth)
		z = 1
		k, p = w.k_normal(i, z)
		f, q = w.f_normal(j, z)
		self.dbg("--> z={0}, {1} vs {2}".format(z, k, f), depth=depth)
		while k == f or (k in 'けゖ' and f in 'がか') :
			z += 1
			if p <= 0 or q <= 0 :
				break
			k, p = w.k_normal(i, z)
			f, q = w.f_normal(j, z)
			self.dbg("--> z={0}, {1} vs {2}".format(z, k, f), depth=depth)
		return w.original(i, j, z-1, z-1) if z > 1 else None

	def match(self, w, i=None, j=None, depth=0) :
		i, j = w.seek(i, j)
		self.dbg(">>> Ruby.match({0}, {1}, {2})".format(w, i, j))
		k, p = w.k_normal(i)
		if k in self.jukujikun :
			yield from self.match_jukujikun(w, i, j, depth)
		if k in self.furigana :
			yield from self.match_kanji(w, i, j, depth)
		else :
			r = self.match_kana(w, i, j, depth)
			if r is not None :
				yield r

	def failed_match_kanji(self, w, i, j, depth=0) :
		self.dbg(">>> Ruby.failed_match_kanji({0}, {1}, {2}, {3})".format(
			w._k_original, w._f_original, i, j
		), depth=depth)
		return list()

	def failed_split(self, w) :
		self.dbg(">>> Ruby.failed_split({0}, {1})".format(w._k_normal, w._f_normal), depth=0)
		return None

	def split(self, kanji, furigana) :
		w = Duplex(kanji, furigana)
		self.dbg(">>> split({0})".format(w))
		s = self._split(w)
		if s is None and self.explicit:
			s = self.failed_split(w)
		return s

	def _split(self, w, i=None, j=None, stack=None, depth=0) :
		#if depth > 10 :
		#	self.dbg("excessive reccursion for {0} / {1}".format(w))
		#	return None

		if stack is None :
			stack = list()

		i, j = w.seek(i, j)
		self.dbg(">>> Ruby.split({0}, {1}, {2}, {3})".format(
			w._k_original, w._f_original, i, j
		), depth=depth)

		# stop conditions
		if i <= 0 : # no more kanji
			if j <= 0 :
				self.dbg("<<< {0}".format(stack), depth=depth)
				return stack
			else :
				return None
		if j <= 0 :
			if self.explicit :
				if i <= 0 :
					self.dbg("<<< {0}".format(stack), depth=depth)
					return stack
				else :
					self.dbg("<<< None", depth=depth)
					return None
			else :
				if i <= 0 :
					self.dbg("<<< {0}".format(stack), depth=depth)
					return stack
				else :
					k, p = w.k_original(i, i)
					self.dbg("<<< Ruby.split: {0}".format([k,] + stack), depth=depth)
					return [k,] + stack

		for k, f, p, q in self.match(w, i, j, depth) :
			self.dbg("--> loop s={0}/{1}, p={2}, q={3}".format(k, f, p, q), depth=depth)

			v = self._split(w, p, q, [(k, f),] + stack, depth+1)

			if v is None :
				self.dbg("<-- continue", depth=depth)
				continue
			else :
				self.dbg("<<< {0}".format(v), depth=depth)
				return v

	def to_html5(self, kanji, furigana, explicit=True, grouped=False) :
		stack = self.split(kanji, furigana)
		if stack is None :
			# TODO dans ce cas on pourrait envisager une séance de rattrappage
			# via l'algo precedent basé sur lcs et diff
			return '<ruby class="r_error">{0}<rt>{1}</ruby>'.format(kanji, furigana)
		else :
			return self.join(stack, grouped)

	def join(self, stack, grouped) :
		stack = [a if a == b else [a, b] for a, b in stack]
		if grouped :
			return '<ruby>{0}<rt>{1}</ruby>'.format(
				'<rb>'.join(v if isinstance(v, str) else v[0] for v in stack),
				'<rt>'.join(v if isinstance(v, str) else v[1] for v in stack)
			)
		else :
			return ''.join(
				(v if isinstance(v, str) else '<ruby>{0}<rt>{1}</ruby>'.format(* v))
				for v in stack
			)

if __name__ == '__main__' :
	k, f = sys.argv[1:]
	u = Ruby(debug=True).default_config()
	print(k, f, '->', u.split(k, f))

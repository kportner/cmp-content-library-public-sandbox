# uncompyle6 version 3.5.0
# Python bytecode 3.6 (3379)
# Decompiled from: Python 2.7.5 (default, Nov 16 2020, 22:23:17)
# [GCC 4.8.5 20150623 (Red Hat 4.8.5-44)]
# Embedded file name: /var/opt/cloudbolt/proserv/xui/bolty_cards/game.py
# Compiled at: 2019-03-02 05:53:40
# Size of source mod 2**32: 9114 bytes
import random

class CardGame(object):
    DECK = {'?':{'short':'CB',
      'long':'Back of Card'},
     '0':{'short':'AC',
      'long':'Ace of Clubs'},
     '1':{'short':'2C',
      'long':'2 of Clubs'},
     '2':{'short':'3C',
      'long':'3 of Clubs'},
     '3':{'short':'4C',
      'long':'4 of Clubs'},
     '4':{'short':'5C',
      'long':'5 of Clubs'},
     '5':{'short':'6C',
      'long':'6 of Clubs'},
     '6':{'short':'7C',
      'long':'7 of Clubs'},
     '7':{'short':'8C',
      'long':'8 of Clubs'},
     '8':{'short':'9C',
      'long':'9 of Clubs'},
     '9':{'short':'10C',
      'long':'10 of Clubs'},
     '10':{'short':'JC',
      'long':'Jack of Clubs'},
     '11':{'short':'QC',
      'long':'Queen of Clubs'},
     '12':{'short':'KC',
      'long':'King of Clubs'},
     '13':{'short':'AD',
      'long':'Ace of Diamonds'},
     '14':{'short':'2D',
      'long':'2 of Diamonds'},
     '15':{'short':'3D',
      'long':'3 of Diamonds'},
     '16':{'short':'4D',
      'long':'4 of Diamonds'},
     '17':{'short':'5D',
      'long':'5 of Diamonds'},
     '18':{'short':'6D',
      'long':'6 of Diamonds'},
     '19':{'short':'7D',
      'long':'7 of Diamonds'},
     '20':{'short':'8D',
      'long':'8 of Diamonds'},
     '21':{'short':'9D',
      'long':'9 of Diamonds'},
     '22':{'short':'10D',
      'long':'10 of Diamonds'},
     '23':{'short':'JD',
      'long':'Jack of Diamonds'},
     '24':{'short':'QD',
      'long':'Queen of Diamonds'},
     '25':{'short':'KD',
      'long':'King of Diamonds'},
     '26':{'short':'AH',
      'long':'Ace of Hearts'},
     '27':{'short':'2H',
      'long':'2 of Hearts'},
     '28':{'short':'3H',
      'long':'3 of Hearts'},
     '29':{'short':'4H',
      'long':'4 of Hearts'},
     '30':{'short':'5H',
      'long':'5 of Hearts'},
     '31':{'short':'6H',
      'long':'6 of Hearts'},
     '32':{'short':'7H',
      'long':'7 of Hearts'},
     '33':{'short':'8H',
      'long':'8 of Hearts'},
     '34':{'short':'9H',
      'long':'9 of Hearts'},
     '35':{'short':'10H',
      'long':'10 of Hearts'},
     '36':{'short':'JH',
      'long':'Jack of Hearts'},
     '37':{'short':'QH',
      'long':'Queen of Hearts'},
     '38':{'short':'KH',
      'long':'King of Hearts'},
     '39':{'short':'AS',
      'long':'Ace of Spades'},
     '40':{'short':'2S',
      'long':'2 of Spades'},
     '41':{'short':'3S',
      'long':'3 of Spades'},
     '42':{'short':'4S',
      'long':'4 of Spades'},
     '43':{'short':'5S',
      'long':'5 of Spades'},
     '44':{'short':'6S',
      'long':'6 of Spades'},
     '45':{'short':'7S',
      'long':'7 of Spades'},
     '46':{'short':'8S',
      'long':'8 of Spades'},
     '47':{'short':'9S',
      'long':'9 of Spades'},
     '48':{'short':'10S',
      'long':'10 of Spades'},
     '49':{'short':'JS',
      'long':'Jack of Spades'},
     '50':{'short':'QS',
      'long':'Queen of Spades'},
     '51':{'short':'KS',
      'long':'King of Spades'}}

    def __init__(self, guess=None):
        print('Inside INIT')
        print('initialing string {}'.format(guess))
        if not guess or guess == 'new':
            self.first_four = self.new_game()
        else:
            parts = guess.split('-')
            if len(parts) != 5:
                self.reset_on_error()
            else:
                self.first_four = '-'.join(parts[:-1])
                print(self.first_four)
            self.guess = parts[(-1)]
        try:
            self.validate()
        except Exception as e:
            print(e)
            self.reset_on_error()

    def new_game(self):
        print('Inside new_game()')
        game = ''
        random_cards = []
        d = 0
        for i in range(0, 5):
            card = None
            while 1:
                if not card or card in random_cards:
                    card = random.randint(0, 51)
                break

            random_cards.append(card)

        random_cards.sort()
        print('Random cards chosen: {}'.format(random_cards))
        for i in range(1, 5):
            a = random_cards[(i - 1)]
            print(a)
            b = random_cards[i]
            print(b)
            if int(a / 13) == int(b / 13):
                print('both cards are of the same suit')
                d = b - a
                random_cards.remove(a)
                random_cards.remove(b)
                if d < 7:
                    game += self.DECK[str(a)]['short'] + '-'
                else:
                    game += self.DECK[str(b)]['short'] + '-'
                    d = 13 + a - b
                break

        print('First card: {}'.format(game))
        print('delta: {}'.format(d))
        print('')
        random_cards = [self.DECK[str(c_idx)]['short'] for c_idx in random_cards]
        game_template = '{}-{}-{}'
        if d == 1:
            game += game_template.format(random_cards[0], random_cards[1], random_cards[2])
        elif d == 2:
            game += game_template.format(random_cards[1], random_cards[0], random_cards[2])
        elif d == 3:
            game += game_template.format(random_cards[2], random_cards[0], random_cards[1])
        elif d == 4:
            game += game_template.format(random_cards[0], random_cards[2], random_cards[1])
        elif d == 5:
            game += game_template.format(random_cards[1], random_cards[2], random_cards[0])
        else:
            game += game_template.format(random_cards[2], random_cards[1], random_cards[0])
        self.guess = 'CB'
        self.message = '\n        <div class="alert alert-info" role="alert">\n            Pick a card...\n        </div>\n        '
        return game

    def validate(self):
        print('Inside validate')
        ordered_cards = [self.from_string_to_index(c) for c in self.first_four.split('-')]
        d = 0
        print(ordered_cards)
        start = ordered_cards[0]
        ordered_cards.remove(start)
        if ordered_cards[0] < ordered_cards[1]:
            if ordered_cards[1] < ordered_cards[2]:
                d = 1
            elif ordered_cards[0] < ordered_cards[2]:
                d = 4
            else:
                d = 5
        elif ordered_cards[0] < ordered_cards[2]:
            d = 2
        elif ordered_cards[1] < ordered_cards[2]:
            d = 3
        else:
            d = 6
        if start % 13 + d > 13:
            d = d - 13
        c = start + d
        print('Expected answer: {}'.format(self.DECK[str(c)]['short']))
        if self.DECK[str(c)]['short'] == self.guess:
            self.message = '\n                <div class="alert alert-success" role="alert">\n                    Congrats, you did it!\n                 </div>\n                 '
        elif self.guess != 'CB':
            print('Guess is {}'.format(self.guess))
            long_guess = self.DECK[str(self.from_string_to_index(self.guess))]['long']
            print(long_guess)
            self.message = '\n                <div class="alert alert-danger" role="alert">\n                   Ok, here is a hint.  It is <b>NOT</b> the <b>{}</b>\n                </div>\n                '.format(long_guess)
            self.guess = 'CB'
        else:
            self.message = '\n                <div class="alert alert-info" role="alert">\n                    C\'mon! Do it for Bolty!\n                 </div>\n                 '

    def reset_on_error(self):
        self.first_four = self.new_game()
        self.message = 'Enter some error message here'

    def from_string_to_index(self, c_str):
        print('Inside from_str_to_idx')
        suit = c_str[(-1)]
        print('Suit: {}'.format(suit))
        multiplier = 3
        if suit == 'C':
            multiplier = 0
        elif suit == 'D':
            multiplier = 1
        elif suit == 'H':
            multiplier = 2
        print('using multiplier {}'.format(multiplier))
        rank = c_str[:-1]
        print('Rank: {}'.format(rank))
        if rank == 'J':
            rank = 10
        elif rank == 'Q':
            rank = 11
        elif rank == 'K':
            rank = 12
        elif rank == 'A':
            rank = 0
        else:
            rank = int(rank) - 1
        print('rank as number = {}'.format(rank))
        return rank + 13 * multiplier

    def get_guess_choices(self):
        choices = []
        for v in self.DECK.values():
            s = v['short']
            l = v['long']
            if s == 'CB':
                choices.append((s, 'No selection'))
            elif s not in self.first_four:
                choices.append((s, l))

        return choices